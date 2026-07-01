from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Mapping, Protocol


class LoggerAction(str, Enum):
    EVENT = 'event'
    START = 'start'
    FINISH = 'finish'
    DONE = 'done'
    FAILED = 'failed'
    SUMMARY = 'summary'


@dataclass(frozen=True)
class LoggerEvent:
    source: str
    action: LoggerAction = LoggerAction.EVENT
    payload: Mapping[str, object] = field(default_factory=dict)
    level: int = logging.INFO


class Logger(Protocol):
    def open(self) -> None:
        ...

    def emit(self, event: LoggerEvent) -> None:
        ...

    def close(self) -> None:
        ...
