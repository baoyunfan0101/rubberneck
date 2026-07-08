from __future__ import annotations

from dataclasses import replace

from ..base import DownloaderResult, DownloaderValue
from ...model import Failure, Request, Response
from .base import DownloaderMiddleware


class ChallengeDownloaderMiddleware(DownloaderMiddleware):
    original_request_meta_key = '_rubberneck_challenge_original_request'
    challenge_count_meta_key = '_rubberneck_challenge_count'
    max_challenge_attempts = 1

    def __init__(
        self,
        max_challenge_attempts: int | None = None,
        original_request_meta_key: str | None = None,
        challenge_count_meta_key: str | None = None,
    ) -> None:
        if max_challenge_attempts is not None:
            if max_challenge_attempts < 1:
                raise ValueError('max_challenge_attempts must be at least 1')
            self.max_challenge_attempts = max_challenge_attempts
        if original_request_meta_key is not None:
            self.original_request_meta_key = original_request_meta_key
        if challenge_count_meta_key is not None:
            self.challenge_count_meta_key = challenge_count_meta_key

    def process_output(self, request: Request, output: DownloaderResult) -> DownloaderResult:
        values = list(output)
        original = request.meta.get(self.original_request_meta_key)  # after a challenge page
        if isinstance(original, Request):
            return self.handle_after_challenge(original, request, values)

        for value in values:
            if isinstance(value, Response) and self.is_challenge_page(request, value):
                if self._challenge_count(request) >= self.max_challenge_attempts:
                    return (Failure(
                        request,
                        RuntimeError('max challenge attempts reached'),
                        'downloader',
                    ),)
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
        original_meta = dict(original_request.meta)
        original_meta[self.challenge_count_meta_key] = self._challenge_count(original_request) + 1
        original_request = replace(original_request, meta=original_meta)
        for value in output:
            if isinstance(value, Request):
                meta = dict(value.meta)
                meta[self.original_request_meta_key] = original_request
                values.append(replace(value, meta=meta))
            else:
                values.append(value)
        return values

    def _challenge_count(self, request: Request) -> int:
        return int(request.meta.get(self.challenge_count_meta_key, 0))
