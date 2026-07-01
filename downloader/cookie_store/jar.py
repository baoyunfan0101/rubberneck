from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable
from threading import RLock

from ...model import Request, Response
from ...registry import ComponentSpec
from .base import CookieStore
from .registry import COOKIE_STORES


class CookieJarRegistry:
    def __init__(
        self,
        max_jars: int = 1,
        default_jar: Hashable = 0,
        store: ComponentSpec | str = 'requests',
    ) -> None:
        if max_jars < 1:
            raise ValueError('max_jars must be at least 1')
        self.max_jars = max_jars  # maximum number of cookie jars
        self.default_jar = default_jar  # default cookie jar key
        self.store = store  # cookie store implementation
        self._stores: OrderedDict[Hashable, CookieStore] = OrderedDict()  # LRU: cookie jar key -> cookie store
        self._lock = RLock()  # allow nested lock acquisition by the same thread

    def add_cookie_header(self, key: Hashable, request: Request) -> None:
        with self._lock:  # guard shared cookie stores
            self._get(key).add_cookie_header(request)  # use the selected cookie store

    def merge(self, key: Hashable, response: Response) -> None:
        with self._lock:  # guard shared cookie stores
            self._get(key).merge(response.cookies)  # use the selected cookie store

    def _get(self, key: Hashable) -> CookieStore:
        if key in self._stores:  # move to end (most recently used)
            self._stores.move_to_end(key)
        else:  # create a new cookie store for a key seen for the first time
            if len(self._stores) >= self.max_jars:
                self._stores.popitem(last=False)  # evict the least recently used jar
            self._stores[key] = self._new_store()
        return self._stores[key]

    def _new_store(self) -> CookieStore:
        if isinstance(self.store, ComponentSpec):
            return COOKIE_STORES.create_spec(self.store)
        return COOKIE_STORES.create(self.store)
