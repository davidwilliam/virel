import asyncio
import json

import pytest

from virel.registry import fresh_registry


@pytest.fixture(autouse=True)
def registry():
    """Isolate each test in its own application registry."""
    yield fresh_registry()
    fresh_registry()


class ASGIResponse:
    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.body = b""
        self.chunks: list[bytes] = []

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    @property
    def json(self):
        return json.loads(self.body)


def asgi_request(app, method: str, path: str, body: bytes = b"",
                 query: str = "") -> ASGIResponse:
    """Drive an ASGI app directly — a minimal in-process test client."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": query.encode(),
        "headers": [],
    }
    response = ASGIResponse()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            raise AssertionError("receive called twice")
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            response.status = message["status"]
            response.headers = {
                k.decode(): v.decode() for k, v in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            if chunk:
                response.chunks.append(chunk)
            response.body += chunk

    asyncio.run(app(scope, receive, send))
    return response
