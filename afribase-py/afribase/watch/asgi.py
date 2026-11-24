"""ASGI integration for FastAPI, Starlette and other ASGI apps.

    from afribase.watch.asgi import WatchMiddleware
    app.add_middleware(WatchMiddleware)        # FastAPI / Starlette
    # or: app = WatchMiddleware(app)            # any ASGI app

Reports exceptions that escape the app (FastAPI/Starlette re-raise unhandled
errors past their exception handlers) and re-raises them, with the request's
path, method and ``X-Watch-Session`` header. HTTPException and other handled
errors are not reported. No framework is imported.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, MutableMapping

from afribase.watch._client import SESSION_HEADER, begin_request, capture_exception, end_request

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]

_HEADER = SESSION_HEADER.lower().encode("latin-1")


class WatchMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]], framework: str = "asgi") -> None:
        self.app = app
        self.framework = framework

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        session = None
        for name, value in scope.get("headers") or []:
            if name.lower() == _HEADER:
                session = value.decode("latin-1")
                break
        path = scope.get("path")
        method = scope.get("method") or ("WS" if scope.get("type") == "websocket" else None)
        token = begin_request(session, path, method)
        status: Dict[str, Any] = {}

        async def send_wrapper(message: Dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status["code"] = message.get("status")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            status.setdefault("code", 500)
            capture_exception(exc, context={"framework": self.framework}, session_id=session,
                              url=path, method=method, status=500)
            raise
        finally:
            end_request(token, status.get("code"))
