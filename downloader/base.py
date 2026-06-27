from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeAlias

from ..logger import LoggerEvent
from ..model import Failure, Request, Response

DownloaderValue: TypeAlias = Request | Response | Failure | LoggerEvent
DownloaderResult: TypeAlias = Iterable[DownloaderValue]


class Downloader(Protocol):
    def open(self) -> None:
        ...

    def fetch(self, request: Request) -> DownloaderResult:
        ...

    def close(self) -> None:
        ...
