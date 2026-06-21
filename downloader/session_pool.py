from __future__ import annotations

from collections.abc import Callable
from queue import Queue

import requests
from requests.adapters import HTTPAdapter

from ..model import Request, Response
from .registry import DOWNLOADERS


# decorator = DOWNLOADERS.register('session_pool');
@DOWNLOADERS.register('session_pool')
class SessionPoolDownloader:
    def __init__(
        self,
        pool_size: int = 8,
        max_host_pools: int = 10,
        timeout: float | tuple[float, float] = (5.0, 30.0),
        session_factory: Callable[[], requests.Session] | None = None,
    ) -> None:
        if pool_size < 1:
            raise ValueError('pool_size must be at least 1')
        if max_host_pools < 1:
            raise ValueError('max_host_pools must be at least 1')
        self.timeout = timeout  # request timeout or connect/read timeout pair
        self._sessions = [
            self._new_session(max_host_pools, session_factory)
            for _ in range(pool_size)
        ]  # session pool
        self._available: Queue[requests.Session] = Queue(maxsize=pool_size)  # idle sessions
        for session in self._sessions:
            self._available.put(session)

    def fetch(self, request: Request) -> Response:
        session = self._available.get()  # block until a session is available
        try:
            self._clear_cookies(session)
            response = session.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                data=request.body,
                timeout=self.timeout,
            )
            try:
                return Response(
                    url=response.url,
                    status=response.status_code,
                    body=response.content,
                    headers=dict(response.headers),
                    request=request,
                    cookies=tuple(response.cookies),
                )
            finally:
                response.close()
        finally:
            self._clear_cookies(session)
            self._available.put(session)

    def close(self) -> None:
        for session in self._sessions:
            session.close()

    @staticmethod
    def _clear_cookies(session: requests.Session) -> None:
        cookies = getattr(session, 'cookies', None)
        if cookies is not None:
            cookies.clear()

    @staticmethod
    def _new_session(
        max_host_pools: int,
        session_factory: Callable[[], requests.Session] | None,
    ) -> requests.Session:
        session = session_factory() if session_factory is not None else requests.Session()
        adapter = HTTPAdapter(
            pool_connections=max_host_pools,  # number of host pools this session caches
            pool_maxsize=1,  # number of connections each host pool keeps
            pool_block=True,  # whether to wait when a host pool is full
        )
        session.mount('http://', adapter)  # use this adapter for http:// URLs
        session.mount('https://', adapter)  # use this adapter for https:// URLs
        return session

# SessionPoolDownloader = decorator(SessionPoolDownloader);
