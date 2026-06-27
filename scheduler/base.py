from __future__ import annotations

from typing import Protocol

from ..model import Request


class Scheduler(Protocol):
    def open(self) -> None:
        ...

    def enqueue(self, request: Request) -> bool:
        ...

    def dequeue(self) -> Request | None:
        ...

    def mark_done(self, request: Request) -> None:
        ...

    def mark_failed(self, request: Request, error: Exception) -> None:
        ...

    def has_pending(self) -> bool:
        ...

    def pending_count(self) -> int:
        ...

    def leased_count(self) -> int:
        ...

    def close(self) -> None:
        ...
