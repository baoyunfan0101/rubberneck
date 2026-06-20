from __future__ import annotations

from http.cookiejar import CookieJar
from threading import Lock
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor
from urllib.request import Request as UrlRequest
from urllib.request import build_opener

from ..model import Request, Response
from .registry import DOWNLOADERS


# decorator = DOWNLOADERS.register("urllib");
@DOWNLOADERS.register("urllib")
class UrllibDownloader:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout  # request timeout in seconds
        self.cookies = CookieJar()  # cookie storage
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))  # opener with cookie support
        self._lock = Lock()  # synchronization lock

    def fetch(self, request: Request) -> Response:
        raw_request = UrlRequest(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method.upper(),
        )
        try:
            with self._lock:  # only one thread may use the opener/cookies at a time
                response = self.opener.open(raw_request, timeout=self.timeout)
        except HTTPError as response:
            return Response(response.url, response.code, response.read(), dict(response.headers.items()), request)
        with response:
            return Response(response.url, response.status, response.read(), dict(response.headers.items()), request)

# UrllibDownloader = decorator(UrllibDownloader);
