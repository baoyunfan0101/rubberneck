from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any

from ..model import Request


@dataclass
class EngineStats:
    enqueued: int = 0  # number of enqueued requests
    filtered: int = 0  # number of filtered requests
    done: int = 0  # number of done work orders
    failed: int = 0  # number of failed work orders


@dataclass
class WorkOrder:
    request: Request  # root request

    downloaders: int = 0  # number of running downloaders
    spiders: int = 0  # number of running spiders
    pipelines: int = 0  # number of running pipelines

    enqueued: int = 0  # number of enqueued requests
    filtered: int = 0  # number of filtered requests
    processed: int = 0  # number of processed items

    payload: dict[str, Any] = field(default_factory=dict)  # collected engine event payloads
    error: Exception | None = None  # final error
    acked: bool = False  # finally acknowledged

    def collect(self, payload: Mapping[str, object]) -> None:
        self.payload.update(payload)

    def is_idle(self) -> bool:
        return self.downloaders == 0 and self.spiders == 0 and self.pipelines == 0
