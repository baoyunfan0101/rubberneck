from __future__ import annotations

from collections.abc import Iterable

from ..model import Response


class SpiderMiddleware:

    def open(self, engine: object) -> None:
        pass

    def process_response(self, response: Response) -> Response:
        return response

    def process_output(
        self, response: Response, output: Iterable[object]
    ) -> Iterable[object]:
        return output

    def close(self, engine: object) -> None:
        pass
