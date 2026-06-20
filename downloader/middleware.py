from __future__ import annotations

from typing import Protocol

from ..model import Request, Response


class DownloaderMiddleware(Protocol):
    def process_request(self, request: Request) -> Request:
        ...

    def process_response(self, request: Request, response: Response) -> Response | Request:
        ...
