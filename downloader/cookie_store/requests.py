from __future__ import annotations

from collections.abc import Iterable
from http.cookiejar import Cookie

import requests
from requests.cookies import RequestsCookieJar, get_cookie_header

from ...model import Request
from .registry import COOKIE_STORES


# decorator = COOKIE_STORES.register('requests');
@COOKIE_STORES.register('requests')
class RequestsCookieStore:
    def __init__(self) -> None:
        self.jar = RequestsCookieJar()  # store and match cookies

    def add_cookie_header(self, request: Request) -> None:
        prepared = requests.Request(
            method=request.method,
            url=request.url,
            headers=dict(request.headers),
        ).prepare()  # convert to PreparedRequest for cookie matching
        cookie_header = get_cookie_header(self.jar, prepared)
        if cookie_header is not None:
            request.headers = {**request.headers, 'Cookie': cookie_header}

    def merge(self, cookies: Iterable[Cookie]) -> None:
        for cookie in cookies:
            self.jar.set_cookie(cookie)

# RequestsCookieStore = decorator(RequestsCookieStore);
