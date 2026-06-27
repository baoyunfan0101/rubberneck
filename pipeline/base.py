from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping, Protocol, TypeAlias

from ..logger import LoggerEvent
from ..spider import Spider

PipelineValue: TypeAlias = Mapping[str, object] | LoggerEvent
PipelineResult: TypeAlias = Iterable[PipelineValue]


class ItemPipeline(Protocol):
    def open(self) -> None:
        ...

    def process_item(self, item: Mapping[str, object], spider: Spider) -> PipelineResult:
        ...

    def close(self) -> None:
        ...
