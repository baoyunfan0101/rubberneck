from __future__ import annotations

from collections.abc import Iterable
from http.cookiejar import Cookie
from typing import Protocol

from ...model import Request


class CookieStore(Protocol):
    def add_cookie_header(self, request: Request) -> None:
        ...

    def merge(self, cookies: Iterable[Cookie]) -> None:
        ...
