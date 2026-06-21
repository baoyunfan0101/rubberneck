from __future__ import annotations

from ...model import Request, Response


class DownloaderMiddleware:
    order = 0

    def open(self, engine: object) -> None:
        pass

    def process_request(self, request: Request) -> Request | Response | None:
        return None

    def process_response(self, request: Request, response: Response) -> Request | Response | None:
        return response

    def process_exception(self, request: Request, error: Exception) -> Request | Response | None:
        return None

    def close(self, engine: object) -> None:
        pass
