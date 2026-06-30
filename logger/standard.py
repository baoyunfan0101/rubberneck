from __future__ import annotations

import logging

from ..engine.state import EngineStats
from .base import Logger, LoggerAction, LoggerEvent
from .registry import LOGGERS


# decorator = LOGGERS.register('standard');
@LOGGERS.register('standard')
class StandardLogger(Logger):
    def __init__(
        self,
        name: str = 'rubberneck',
        logger: logging.Logger | None = None,
        summary_every: int = 0,
    ) -> None:
        self.logger = logger or logging.getLogger(name)
        self.summary_every = summary_every
        self._last_summary = EngineStats()

    def emit(self, event: LoggerEvent) -> None:
        if event.action == LoggerAction.SUMMARY:
            self._log_summary(event)
        else:
            self._log(event)

    def _log(self, event: LoggerEvent) -> None:
        payload = event.payload
        parts: list[object] = ['[%s] %s:', event.action.upper(), event.source]
        fmt = parts[0]
        for key, value in payload.items():
            fmt += f' {key}=%s'
            parts.append(value)
        parts[0] = fmt
        self.logger.log(event.level, *parts)

    def _log_summary(self, event: LoggerEvent) -> None:
        summary = event.payload.get('summary')
        if not isinstance(summary, EngineStats):
            return
        if not (0 < self.summary_every <= summary.done - self._last_summary.done):
            return
        self.logger.info(
            '[%s] %s: enqueued=%s(+%s) filtered=%s(+%s) done=%s(+%s) failed=%s(+%s)',
            event.action.upper(),
            event.source,
            summary.enqueued,
            summary.enqueued - self._last_summary.enqueued,
            summary.filtered,
            summary.filtered - self._last_summary.filtered,
            summary.done,
            summary.done - self._last_summary.done,
            summary.failed,
            summary.failed - self._last_summary.failed,
        )
        self._last_summary = EngineStats(
            done=summary.done,
            failed=summary.failed,
            enqueued=summary.enqueued,
            filtered=summary.filtered,
        )

# StandardLogger = decorator(StandardLogger);
