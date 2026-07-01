from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping, Protocol, TypeAlias

from ..logger import LoggerEvent

PipelineValue: TypeAlias = Mapping[str, object] | LoggerEvent
PipelineResult: TypeAlias = Iterable[PipelineValue]


class Pipeline(Protocol):
    def open(self) -> None:
        ...

    def process_item(self, item: Mapping[str, object]) -> PipelineResult:
        ...

    def close(self) -> None:
        ...
