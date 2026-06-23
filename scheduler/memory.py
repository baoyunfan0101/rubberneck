from __future__ import annotations

import heapq
import itertools
from threading import Lock

from ..model import CrawlTask, Request
from .registry import SCHEDULERS


# decorator = SCHEDULERS.register('memory');
@SCHEDULERS.register('memory')
class MemoryScheduler:
    def __init__(self) -> None:
        self._queue: list[tuple[int, int, CrawlTask]] = []  # min_heap: (priority, sequence number, crawl task)
        self._seen: set[tuple[str, str, bytes | None]] = set()  # seen: fingerprint
        self._leased: dict[int, CrawlTask] = {}  # leased: crawl task
        self._done: set[int] = set()  # done: task id
        self._failed: dict[int, str] = {}  # failed: {task id -> error}
        self._task_ids = itertools.count(1)  # task id
        self._sequence = itertools.count()  # task sequence number
        self._lock = Lock()

    def enqueue(self, request: Request) -> bool:
        with self._lock:
            fingerprint = request.fingerprint()  # fingerprint: method.upper() + url + body
            if not request.dont_filter and fingerprint in self._seen:  # skip duplicate requests unless dont_filter
                return False
            if not request.dont_filter:
                self._seen.add(fingerprint)
            task = CrawlTask(
                id=next(self._task_ids),
                request=request,
            )
            self._push(task)
            return True

    def claim(self) -> CrawlTask | None:
        with self._lock:
            if not self._queue:
                return None
            task = heapq.heappop(self._queue)[2]
            self._leased[task.id] = task
            return task

    def ack(self, task: CrawlTask) -> None:
        with self._lock:
            self._require_lease(task)
            self._leased.pop(task.id)
            self._done.add(task.id)

    def fail(self, task: CrawlTask, error: Exception) -> None:
        with self._lock:
            self._require_lease(task)
            self._leased.pop(task.id)
            self._failed[task.id] = str(error)

    def retry(self, task: CrawlTask, error: Exception) -> None:
        with self._lock:
            self._require_lease(task)
            self._leased.pop(task.id)
            self._push(CrawlTask(task.id, task.request, task.attempt + 1))

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

    def _push(self, task: CrawlTask) -> None:
        heapq.heappush(
            self._queue,
            (-task.request.priority, next(self._sequence), task),
        )  # push into the min-heap by priority, then sequence number

    def _require_lease(self, task: CrawlTask) -> None:
        if self._leased.get(task.id) != task:
            raise RuntimeError(f'task is not leased: {task.id}')

# MemoryScheduler = decorator(MemoryScheduler);
