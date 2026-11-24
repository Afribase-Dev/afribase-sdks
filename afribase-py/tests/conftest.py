import json

import httpx
import pytest

import afribase._http as _http


class MockServer:
    """Routes the SDK's httpx calls to a handler and records every request."""

    def __init__(self):
        self.requests = []
        self.routes = []

    def on(self, method, path_contains, status=200, json_body=None, text=None, headers=None):
        self.routes.append((method, path_contains, status, json_body, text, headers or {}))
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for method, part, status, body, text, headers in reversed(self.routes):
            if request.method == method and part in str(request.url):
                if text is not None:
                    return httpx.Response(status, text=text, headers=headers)
                if body is None:
                    return httpx.Response(status, headers=headers)
                return httpx.Response(status, json=body, headers=headers)
        return httpx.Response(404, json={"message": "no route"})

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self):
        return json.loads(self.last.content or b"null")


@pytest.fixture
def server(monkeypatch):
    srv = MockServer()
    transport = httpx.MockTransport(srv.handler)
    real_client, real_async = httpx.Client, httpx.AsyncClient

    def client(*a, **kw):
        kw["transport"] = transport
        return real_client(*a, **kw)

    def async_client(*a, **kw):
        kw["transport"] = transport
        return real_async(*a, **kw)

    monkeypatch.setattr(_http.httpx, "Client", client)
    monkeypatch.setattr(_http.httpx, "AsyncClient", async_client)
    yield srv
    monkeypatch.setattr(_http.httpx, "Client", real_client)
