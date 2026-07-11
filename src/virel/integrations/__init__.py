"""Deployment integrations (SPEC 9.4, 20.4).

A Virel application is a standard ASGI app, so it composes with existing
Python web stacks. ``mount`` attaches Virel to a FastAPI or Starlette
application as the fallback for everything their routers do not handle,
and ``PathMount`` dispatches path prefixes to other ASGI apps (an API, a
legacy Django application) while Virel serves the rest.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class PathMount:
    """Dispatch requests by path prefix, with Virel (or any app) as the
    default. Prefix apps receive standard submount semantics: the prefix
    moves from ``path`` to ``root_path``.

        application = PathMount(
            default=create_asgi_app(),
            mounts={"/api": fastapi_app, "/legacy": django_asgi},
        )
    """

    def __init__(self, default: Any, mounts: dict[str, Any] | None = None) -> None:
        self.default = default
        self.mounts = sorted((mounts or {}).items(),
                             key=lambda item: len(item[0]), reverse=True)
        for prefix, _ in self.mounts:
            if not prefix.startswith("/") or prefix == "/" or prefix.endswith("/"):
                raise ValueError(
                    f"mount prefix {prefix!r} must start with '/', not end "
                    "with '/', and not be the root (the default app owns it)")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.default(scope, receive, send)
            return
        path = scope.get("path", "/")
        for prefix, app in self.mounts:
            if path == prefix or path.startswith(prefix + "/"):
                child = dict(scope)
                child["root_path"] = scope.get("root_path", "") + prefix
                child["path"] = path[len(prefix):] or "/"
                await app(child, receive, send)
                return
        await self.default(scope, receive, send)


def mount(app: Any, virel_app: Any | None = None, path: str = "/") -> None:
    """Mount a Virel application inside FastAPI or Starlette.

    Virel serves as the fallback for every path the host's own routes do
    not match, which is how the frameworks treat a root mount:

        from fastapi import FastAPI
        from virel.integrations import mount

        app = FastAPI()
        mount(app)
    """
    if path != "/":
        raise ValueError(
            "Virel currently mounts at the root path only; put API routes "
            "at prefixes on the host app, or use PathMount to give other "
            "apps their prefixes."
        )
    if virel_app is None:
        from ..server import create_asgi_app
        virel_app = create_asgi_app()
    app.mount(path, virel_app)
