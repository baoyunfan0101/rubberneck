from __future__ import annotations

from typing import Mapping, Protocol

from ..spider import Spider


class ItemPipeline(Protocol):
    def process_item(self, item: Mapping[str, object], spider: Spider) -> Mapping[str, object] | None:
        ...
