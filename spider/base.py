from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping

from ..model import Request, Response


class Spider:
    name = 'unnamed'

    def start_requests(self) -> Iterable[Request]:
        raise NotImplementedError

    def parse(self, response: Response) -> Iterable[Request | Mapping[str, object]]:
        raise NotImplementedError
