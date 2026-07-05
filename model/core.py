from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from http.cookiejar import Cookie
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..logger import LogRecord


class EngineAction(str, Enum):
    NONE = ''
    COLLECT = 'collect'
    STOP_NOW = 'stop_now'
    STOP_GRACEFULLY = 'stop_gracefully'


@dataclass(frozen=True)
class EngineEvent:
    action: EngineAction = EngineAction.NONE
    payload: Mapping[str, object] = field(default_factory=dict)
    log: LogRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, EngineAction):  # normalize to EngineAction
            object.__setattr__(self, 'action', EngineAction(self.action))
        if self.log is not None:
            from ..logger import LogRecord

            if not isinstance(self.log, LogRecord):
                raise TypeError('EngineEvent.log must be a LogRecord or None')


@dataclass
class Failure:
    value: object
    exception: Exception
    stage: str = ''

    def __str__(self) -> str:
        if self.stage:
            return f'{self.stage}: {self.value} failed: {self.exception}'
        return f'{self.value} failed: {self.exception}'


@dataclass(frozen=True)
class Item(Mapping[str, object]):
    data: Mapping[str, object] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


@dataclass
class Request:
    url: str
    method: str = 'GET'
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def fingerprint(self) -> tuple[str, str, bytes | None]:
        return self.method.upper(), self.url, self.body

    def __str__(self) -> str:
        return f'{self.method} {self.url}'


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    request: Request | None = None
    cookies: tuple[Cookie, ...] = ()

    def __str__(self) -> str:
        return f'{self.status} {self.url}'

    @property
    def text(self) -> str:
        content_type = self.headers.get('content-type', '')
        charset = 'utf-8'
        if 'charset=' in content_type.lower():
            charset = (
                content_type.lower().split('charset=', 1)[1].split(';', 1)[0].strip()
            )
        return self.body.decode(charset, errors='replace')
