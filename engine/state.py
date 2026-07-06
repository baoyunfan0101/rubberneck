from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any

from ..model import Request


def _default_payload() -> dict[str, Any]:
    return {
        'enqueued': 0,
        'filtered': 0,
        'processed': 0,
    }


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

    payload: dict[str, Any] = field(default_factory=_default_payload)  # collected engine event payloads
    error: BaseException | None = None  # final error
    acked: bool = False  # finally acknowledged

    def collect(self, payload: Mapping[str, object]) -> None:
        for key, value in payload.items():
            if isinstance(value, int) and not isinstance(value, bool):
                self.count(key, value)
            else:
                self.payload[key] = value

    def count(self, key: str, amount: int = 1) -> None:
        self.payload[key] = int(self.payload.get(key, 0)) + amount

    def is_idle(self) -> bool:
        return self.downloaders == 0 and self.spiders == 0 and self.pipelines == 0
