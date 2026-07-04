from __future__ import annotations

from dataclasses import dataclass, field
from http.cookiejar import Cookie
from typing import Any, Mapping


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


@dataclass
class Failure:
    value: object
    exception: Exception
    stage: str = ''

    def __str__(self) -> str:
        if self.stage:
            return f'{self.stage}: {self.value} failed: {self.exception}'
        return f'{self.value} failed: {self.exception}'
