from __future__ import annotations

from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from urllib.parse import urlsplit

from requests.cookies import morsel_to_cookie

from ..model import Request, Response
from .registry import DOWNLOADERS


# decorator = DOWNLOADERS.register('urllib');
@DOWNLOADERS.register('urllib')
class UrllibDownloader:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout  # request timeout in seconds

    def fetch(self, request: Request) -> Response:
        raw_request = UrlRequest(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method.upper(),
        )
        try:
            raw_response = urlopen(raw_request, timeout=self.timeout)
        except HTTPError as e:
            raw_response = e
        with raw_response:
            return Response(
                url=raw_response.url,
                status=(
                    raw_response.status
                    if hasattr(raw_response, 'status')
                    else raw_response.code
                ),
                body=raw_response.read(),
                headers=dict(raw_response.headers.items()),
                request=request,
                cookies=self._cookies(raw_response),
            )

    def close(self) -> None:
        pass

    @staticmethod
    def _cookies(raw_response) -> tuple:
        cookies = []
        host = urlsplit(raw_response.url).hostname or ''
        for value in raw_response.headers.get_all('Set-Cookie', []):
            parsed = SimpleCookie()
            parsed.load(value)
            for morsel in parsed.values():
                if not morsel['domain']:
                    morsel['domain'] = host
                if not morsel['path']:
                    morsel['path'] = '/'
                cookies.append(morsel_to_cookie(morsel))
        return tuple(cookies)

# UrllibDownloader = decorator(UrllibDownloader);
