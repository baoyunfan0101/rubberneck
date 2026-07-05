from __future__ import annotations

from collections.abc import Iterable
import logging

from ..engine.state import EngineStats
from .base import Logger, LoggerAction, LogRecord
from .registry import LOGGERS


# decorator = LOGGERS.register('standard');
@LOGGERS.register('standard')
class StandardLogger(Logger):
    def __init__(
        self,
        name: str = 'rubberneck',
        logger: logging.Logger | None = None,
        summary_every: int = 0,
        actions: Iterable[LoggerAction | str] | None = None,
    ) -> None:
        self.logger = logger or logging.getLogger(name)
        self.summary_every = summary_every
        self.actions = None if actions is None else {LoggerAction(action) for action in actions}
        self._last_summary = EngineStats()

    def open(self) -> None:
        pass

    def emit(self, event: LogRecord) -> None:
        if self.actions is not None and event.action not in self.actions:
            return
        if event.action == LoggerAction.SUMMARY:
            self._log_summary(event)
        else:
            self._log(event)

    def close(self) -> None:
        pass

    def _log(self, event: LogRecord) -> None:
        parts: list[object] = ['[%s] %s:', event.action.value.upper(), event.source]
        fmt = parts[0]
        for key, value in event.payload.items():
            fmt += f' {key.replace("%", "%%")}=%s'  # % -> %%
            parts.append(value)
        parts[0] = fmt
        self.logger.log(event.level, *parts)

    def _log_summary(self, event: LogRecord) -> None:
        stats = event.payload.get('stats')
        if not isinstance(stats, EngineStats):
            return
        if not (0 < self.summary_every <= stats.done - self._last_summary.done):
            return
        self.logger.info(
            '''
            [%s] %s: enqueued=%s(+%s) filtered=%s(+%s) done=%s(+%s) failed=%s(+%s) pending=%s leased=%s
            ''',
            event.action.value.upper(),
            event.source,
            stats.enqueued,
            stats.enqueued - self._last_summary.enqueued,
            stats.filtered,
            stats.filtered - self._last_summary.filtered,
            stats.done,
            stats.done - self._last_summary.done,
            stats.failed,
            stats.failed - self._last_summary.failed,
            event.payload.get('pending'),
            event.payload.get('leased'),
        )
        self._last_summary = EngineStats(
            done=stats.done,
            failed=stats.failed,
            enqueued=stats.enqueued,
            filtered=stats.filtered,
        )

# StandardLogger = decorator(StandardLogger);
