from __future__ import annotations

from typing import Protocol

from ..model import CrawlTask, Request


class Scheduler(Protocol):
    def open(self) -> None:
        ...

    def enqueue(self, request: Request) -> bool:
        ...

    def dequeue(self) -> CrawlTask | None:
        ...

    def mark_done(self, task: CrawlTask) -> None:
        ...

    def mark_failed(self, task: CrawlTask, error: Exception) -> None:
        ...

    def requeue(self, task: CrawlTask, error: Exception) -> None:
        ...

    def has_pending(self) -> bool:
        ...

    def pending_count(self) -> int:
        ...

    def leased_count(self) -> int:
        ...

    def close(self) -> None:
        ...
