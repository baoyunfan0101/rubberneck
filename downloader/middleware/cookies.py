from __future__ import annotations

from collections.abc import Hashable

from ..cookie_store import CookieJarRegistry
from ..base import DownloaderResult
from ...model import Request, Response
from ...registry import ComponentSpec
from .base import DownloaderMiddleware
from .registry import DOWNLOADER_MIDDLEWARES


# decorator = DOWNLOADER_MIDDLEWARES.register('cookies');
@DOWNLOADER_MIDDLEWARES.register('cookies')
class CookiesDownloaderMiddleware(DownloaderMiddleware):
    order = 700  # execution order among same-type middlewares

    def __init__(
        self,
        registry: CookieJarRegistry | None = None,
        key: str = 'cookiejar',
        max_jars: int = 1,
        store: ComponentSpec | str = 'requests',
    ) -> None:
        self.registry = registry or CookieJarRegistry(max_jars=max_jars, store=store)
        self.key = key

    def process_input(self, request: Request) -> Request:
        self.registry.add_cookie_header(self._key(request), request)
        return request

    def process_output(
        self,
        request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        values = []
        for value in output:
            if isinstance(value, Response):
                self.registry.merge(self._key(request), value)
            values.append(value)
        return values

    def _key(self, request: Request) -> Hashable:
        value = request.meta.get(self.key, self.registry.default_jar)
        if not isinstance(value, Hashable):
            raise TypeError(f'request.meta[{self.key!r}] must be hashable')
        return value

# CookiesDownloaderMiddleware = decorator(CookiesDownloaderMiddleware);
