from __future__ import annotations

from typing import Protocol

from ..model import Request, Response


class Downloader(Protocol):
    def fetch(self, request: Request) -> Response:
        ...
