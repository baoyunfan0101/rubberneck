from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Protocol


class LoggerAction(str, Enum):
    EVENT = 'event'
    START = 'start'
    FINISH = 'finish'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    DONE = 'done'
    FAILED = 'failed'
    SUMMARY = 'summary'


@dataclass(frozen=True)
class LogRecord(Mapping[str, object]):
    source: str
    action: LoggerAction = LoggerAction.EVENT
    payload: Mapping[str, object] = field(default_factory=dict)
    level: int = logging.INFO

    def __post_init__(self) -> None:
        if not isinstance(self.action, LoggerAction):
            object.__setattr__(self, 'action', LoggerAction(self.action))

    def __getitem__(self, key: str) -> object:
        if key == 'source':
            return self.source
        if key == 'action':
            return self.action
        if key == 'payload':
            return self.payload
        if key == 'level':
            return self.level
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(('source', 'action', 'payload', 'level'))

    def __len__(self) -> int:
        return 4


class Logger(Protocol):
    def open(self) -> None:
        ...

    def emit(self, event: LogRecord) -> None:
        ...

    def close(self) -> None:
        ...
