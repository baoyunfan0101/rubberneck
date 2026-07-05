from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeAlias

from ..model import EngineEvent, Failure, Request, Response

DownloaderValue: TypeAlias = Request | Response | Failure | EngineEvent
DownloaderResult: TypeAlias = Iterable[DownloaderValue]


class Downloader(Protocol):
    def open(self) -> None:
        ...

    def fetch(self, request: Request) -> DownloaderResult:
        ...

    def close(self) -> None:
        ...
