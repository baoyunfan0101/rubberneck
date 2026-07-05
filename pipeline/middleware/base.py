from __future__ import annotations

from ..base import PipelineResult
from ...model import Item


class PipelineMiddleware:
    order = 0

    def open(self) -> None:
        pass

    def process_input(self, item: Item) -> Item:
        return item

    def process_output(
        self,
        item: Item,
        output: PipelineResult,
    ) -> PipelineResult:
        return output

    def close(self) -> None:
        pass
