from __future__ import annotations

from dataclasses import replace

from ..base import DownloaderResult, DownloaderValue
from ...model import Failure, Request, Response
from .base import DownloaderMiddleware


class ChallengeDownloaderMiddleware(DownloaderMiddleware):
    original_request_meta_key = '_rubberneck_challenge_original_request'

    def process_output(self, request: Request, output: DownloaderResult) -> DownloaderResult:
        values = list(output)
        original = request.meta.get(self.original_request_meta_key)  # after a challenge page
        if isinstance(original, Request):
            return self.handle_after_challenge(original, request, values)

        for value in values:
            if isinstance(value, Response) and self.is_challenge_page(request, value):
                return self._remember_original_request(
                    request,
                    self.handle_challenge_page(request, value),
                )
        return values

    def is_challenge_page(self, request: Request, response: Response) -> bool:
        return False

    def handle_challenge_page(self, request: Request, response: Response) -> DownloaderResult:
        raise NotImplementedError

    def handle_after_challenge(
        self,
        original_request: Request,
        challenge_request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        values = list(output)
        if any(isinstance(value, Failure) for value in values):
            return values
        return (original_request,)

    def _remember_original_request(
        self,
        original_request: Request,
        output: DownloaderResult,
    ) -> DownloaderResult:
        values: list[DownloaderValue] = []
        for value in output:
            if isinstance(value, Request):
                meta = dict(value.meta)
                meta[self.original_request_meta_key] = original_request
                values.append(replace(value, meta=meta))
            else:
                values.append(value)
        return values
