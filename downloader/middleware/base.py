from __future__ import annotations

from typing import Protocol

from ...model import Request, Response


class DownloaderMiddleware(Protocol):
    def open(self, engine: object) -> None:
        ...

    def process_request(self, request: Request) -> Request | Response | None:
        ...

    def process_response(self, request: Request, response: Response) -> Request | Response | None:
        ...

    def process_exception(self, request: Request, error: Exception) -> Request | Response | None:
        ...

    def close(self, engine: object) -> None:
        ...
