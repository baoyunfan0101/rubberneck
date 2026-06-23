from __future__ import annotations

from typing import Protocol

from ..model import CrawlTask, Request


class Scheduler(Protocol):
    def enqueue(self, request: Request) -> bool:
        ...

    def claim(self) -> CrawlTask | None:
        ...

    def ack(self, task: CrawlTask) -> None:
        ...

    def fail(self, task: CrawlTask, error: Exception) -> None:
        ...

    def retry(self, task: CrawlTask, error: Exception) -> None:
        ...

    def has_pending(self) -> bool:
        ...

    def pending_count(self) -> int:
        ...

    def leased_count(self) -> int:
        ...

    def close(self) -> None:
        ...
