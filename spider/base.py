from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping, TypeAlias

from ..logger import LoggerEvent
from ..model import Failure, Request, Response

SpiderValue: TypeAlias = Request | Mapping[str, object] | Failure | LoggerEvent
SpiderResult: TypeAlias = Iterable[SpiderValue]


class Spider:
    name = 'unnamed'

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def start_requests(self) -> Iterable[Request]:
        raise NotImplementedError

    def parse(self, response: Response) -> SpiderResult:
        raise NotImplementedError
