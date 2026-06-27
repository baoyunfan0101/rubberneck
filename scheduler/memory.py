from __future__ import annotations

import heapq
import itertools
from threading import Lock

from ..model import Request
from .registry import SCHEDULERS


# decorator = SCHEDULERS.register('memory');
@SCHEDULERS.register('memory')
class MemoryScheduler:
    def __init__(self) -> None:
        self._queue: list[tuple[int, int, Request]] = []  # min_heap: (priority, sequence number, request)
        self._seen: set[tuple[str, str, bytes | None]] = set()  # seen: fingerprint
        self._leased: dict[tuple[str, str, bytes | None], Request] = {}  # leased: {fingerprint -> request}
        self._done: set[tuple[str, str, bytes | None]] = set()  # done: fingerprint
        self._failed: dict[tuple[str, str, bytes | None], str] = {}  # failed: {fingerprint -> error}
        self._sequence = itertools.count()  # request sequence number
        self._lock = Lock()

    def open(self) -> None:
        pass

    def enqueue(self, request: Request) -> bool:
        with self._lock:
            fingerprint = request.fingerprint()  # fingerprint: method.upper() + url + body
            if fingerprint in self._seen:  # skip duplicate requests
                return False
            self._seen.add(fingerprint)
            self._push(request)
            return True

    def dequeue(self) -> Request | None:
        with self._lock:
            if not self._queue:
                return None
            request = heapq.heappop(self._queue)[2]
            self._leased[request.fingerprint()] = request
            return request

    def mark_done(self, request: Request) -> None:
        with self._lock:
            fingerprint = request.fingerprint()
            self._require_lease(request)
            self._leased.pop(fingerprint)
            self._done.add(fingerprint)

    def mark_failed(self, request: Request, error: Exception) -> None:
        with self._lock:
            fingerprint = request.fingerprint()
            self._require_lease(request)
            self._leased.pop(fingerprint)
            self._failed[fingerprint] = str(error)

    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._queue)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    def leased_count(self) -> int:
        with self._lock:
            return len(self._leased)

    def close(self) -> None:
        pass

    def _push(self, request: Request) -> None:
        heapq.heappush(
            self._queue,
            (-request.priority, next(self._sequence), request),
        )  # push into the min-heap by priority, then sequence number

    def _require_lease(self, request: Request) -> None:
        fingerprint = request.fingerprint()
        if self._leased.get(fingerprint) != request:
            raise RuntimeError(f'request is not leased: {request.url}')

# MemoryScheduler = decorator(MemoryScheduler);
