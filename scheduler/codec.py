from __future__ import annotations

import base64
import json
from typing import Protocol

from ..model import Request


class RequestCodec(Protocol):
    def encode(self, request: Request) -> str:
        ...

    def decode(self, value: str) -> Request:
        ...


class JsonRequestCodec:
    def encode(self, request: Request) -> str:
        if request.callback is not None or request.errback is not None:
            raise TypeError('SQLiteScheduler cannot persist Request callbacks or errbacks')
        try:
            return json.dumps(
                {
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'body': base64.b64encode(request.body).decode() if request.body else None,
                    'meta': request.meta,
                    'priority': request.priority,
                    'dont_filter': request.dont_filter,
                },
                separators=(',', ':'),
            )
        except TypeError as error:
            raise TypeError('SQLiteScheduler requires JSON-serializable Request metadata') from error

    def decode(self, value: str) -> Request:
        data = json.loads(value)
        return Request(
            url=data['url'],
            method=data['method'],
            headers=data['headers'],
            body=base64.b64decode(data['body']) if data['body'] is not None else None,
            meta=data['meta'],
            priority=data['priority'],
            dont_filter=data['dont_filter'],
        )
