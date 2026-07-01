from __future__ import annotations

from ...model import Request
from ..base import DownloaderResult


class DownloaderMiddleware:
    order = 0

    def open(self) -> None:
        pass

    def process_input(
        self,
        request: Request,
    ) -> Request:
        return request

    def process_output(
        self,
        request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        return output

    def close(self) -> None:
        pass
