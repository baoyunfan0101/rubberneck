from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    options: Mapping[str, object] = field(default_factory=dict)
    order: int = 0
