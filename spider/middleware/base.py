from __future__ import annotations

from ...model import Response
from ..base import SpiderResult


class SpiderMiddleware:
    order = 0

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
