from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeAlias

from ..model import EngineEvent, Failure, Item

PipelineValue: TypeAlias = Failure | EngineEvent
PipelineResult: TypeAlias = Iterable[PipelineValue]


class Pipeline(Protocol):
    def open(self) -> None:
        ...

    def process_item(self, item: Item) -> PipelineResult:
        ...

    def close(self) -> None:
        ...
