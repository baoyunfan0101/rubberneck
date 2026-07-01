from __future__ import annotations

from typing import Mapping

from ..base import PipelineResult


class PipelineMiddleware:
    order = 0

    def open(self) -> None:
        pass

    def process_input(self, item: Mapping[str, object]) -> Mapping[str, object]:
        return item

    def process_output(
        self,
        item: Mapping[str, object],
        output: PipelineResult,
    ) -> PipelineResult:
        return output

    def close(self) -> None:
        pass
