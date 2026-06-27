from __future__ import annotations

from ...logger import LoggerEvent
from ...model import Request, Response
from ..base import DownloaderResult


class DownloaderMiddleware:
    order = 0

    def open(self) -> None:
        pass

    def process_input(self, request: Request) -> Request | Response | LoggerEvent | None:
        return None

    def process_output(
        self,
        request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        return output

    def close(self) -> None:
        pass
