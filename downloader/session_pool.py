from __future__ import annotations

from collections.abc import Callable
from threading import Condition

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
        self._availability = Condition()  # session assignment lock
        self._busy = [False for _ in self._sessions]  # session busy states
        self._session_ids: dict[str, int] = {}  # session_id -> session index

    def fetch(self, request: Request) -> Response:
        index = self._acquire_session(request)
        try:
            response = self._sessions[index].request(
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
                )
            finally:
                response.close()
        finally:
            self._release_session(index)

    def close(self) -> None:
        for session in self._sessions:
            session.close()

    def _acquire_session(self, request: Request) -> int:
        session_id = request.meta.get('session_id')
        with self._availability:
            if session_id is not None:  # preserve session affinity when possible
                key = str(session_id)
                if key not in self._session_ids:  # assign a session to a new session_id
                    self._session_ids[key] = self._wait_for_idle_session(set(self._session_ids.values()))
                index = self._session_ids[key]
                while self._busy[index]:  # wait until the assigned session becomes idle
                    self._availability.wait()
            else:
                index = self._wait_for_idle_session()  # release the lock, wait until notified, then reacquire the lock
            self._busy[index] = True
            return index

    def _release_session(self, index: int) -> None:
        with self._availability:
            self._busy[index] = False
            self._availability.notify_all()  # wake up threads waiting for an idle session

    def _wait_for_idle_session(self, assigned: set[int] | None = None) -> int:
        # assigned: session indexes already bound to session_ids
        while True:
            for index, busy in enumerate(self._busy):  # prefer a session that is idle and unbound
                if not busy and (assigned is None or index not in assigned):
                    return index
            if assigned:  # fall back to any idle session
                for index, busy in enumerate(self._busy):
                    if not busy:
                        return index
            self._availability.wait()  # release the lock, wait until notified, then reacquire the lock

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
