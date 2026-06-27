from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping

from ..logger import LoggerEvent
from ..model import Request, Response
from .base import SpiderResult


class SpiderMiddleware:
    order = 0  # execution order among same-type middlewares

    def open(self) -> None:
        pass

    def process_input(self, response: Response) -> Response:
        return response

    def process_output(
        self,
        response: Response,
        output: SpiderResult,
    ) -> SpiderResult:
        return output

    def close(self) -> None:
        pass
