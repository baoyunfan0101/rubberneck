from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
import logging
from typing import Mapping
from typing import Protocol


class LoggerAction(StrEnum):
    EVENT = 'event'
    START = 'start'
    FINISH = 'finish'
    DONE = 'done'
    FAILED = 'failed'
    SUMMARY = 'summary'


@dataclass(frozen=True)
class LoggerEvent:
    source: str
    action: LoggerAction | str = LoggerAction.EVENT
    payload: Mapping[str, object] = field(default_factory=dict)
    level: int = logging.INFO


class Logger(Protocol):
    def emit(self, event: LoggerEvent) -> None:
        ...
