from __future__ import annotations

from dataclasses import replace

from ...model import Request
from ..base import DownloaderResult, DownloaderValue
from .base import DownloaderMiddleware
from .registry import DOWNLOADER_MIDDLEWARES


@DOWNLOADER_MIDDLEWARES.register('referer')
class RefererDownloaderMiddleware(DownloaderMiddleware):
    order = -100

    def __init__(
        self,
        meta_key: str = 'parent_url',
        header_name: str = 'Referer',
    ) -> None:
        self.meta_key = meta_key
        self.header_name = header_name

    def process_input(self, request: Request) -> Request:
        parent_url = request.meta.get(self.meta_key)
        if not isinstance(parent_url, str) or not parent_url:
            return request
        if self.header_name in request.headers:
            return request

        headers = dict(request.headers)
        headers[self.header_name] = parent_url
        return replace(request, headers=headers)

    def process_output(
        self,
        request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        values: list[DownloaderValue] = []
        for value in output:
            if isinstance(value, Request):
                meta = dict(value.meta)
                meta.setdefault(self.meta_key, request.url)
                values.append(replace(value, meta=meta))
            else:
                values.append(value)
        return values
