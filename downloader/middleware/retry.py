from __future__ import annotations

from dataclasses import replace

from ..base import DownloaderResult, DownloaderValue
from ...model import Failure, Request
from .base import DownloaderMiddleware


class RetryDownloaderMiddleware(DownloaderMiddleware):
    retry_meta_key = '_rubberneck_retry'

    def __init__(self, max_retries: int = 1) -> None:
        if max_retries < 0:
            raise ValueError('max_retries must be non-negative')
        self.max_retries = max_retries

    def process_output(self, request: Request, output: DownloaderResult) -> DownloaderResult:
        values = list(output)
        for value in values:
            if self.should_retry(request, value):
                return self._retry(request, value)
        return values

    def should_retry(self, request: Request, value: DownloaderValue) -> bool:
        return isinstance(value, Failure)

    def build_retry_request(
        self,
        request: Request,
        value: DownloaderValue,
        next_retry: int,
    ) -> Request:
        meta = dict(request.meta)
        meta[self.retry_meta_key] = next_retry
        return replace(request, meta=meta)

    def _retry(self, request: Request, value: DownloaderValue) -> DownloaderResult:
        current_retry = int(request.meta.get(self.retry_meta_key, 0))  # current retry count
        if current_retry >= self.max_retries:
            return (Failure(request, RuntimeError(f'max retries reached: {value!r}')),)
        next_retry = current_retry + 1
        return (self.build_retry_request(request, value, next_retry),)
