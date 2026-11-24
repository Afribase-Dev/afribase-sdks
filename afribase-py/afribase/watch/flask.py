"""Flask integration: ``init_flask(app)``.

Reports unhandled exceptions through Flask's ``got_request_exception``
signal (sent for errors that become a 500) with the request's path, method
and ``X-Watch-Session`` header. Flask is imported only when called.
"""

from __future__ import annotations

from typing import Any

from afribase.watch._client import begin_request, capture_exception, end_request

_TOKEN = "_afribase_watch_token"
_STATUS = "_afribase_watch_status"


def init_flask(app: Any) -> Any:
    from flask import g, got_request_exception, request

    def _watch_before() -> None:
        setattr(g, _TOKEN, begin_request(request.headers.get("X-Watch-Session"), request.path, request.method))

    def _watch_after(response: Any) -> Any:
        setattr(g, _STATUS, getattr(response, "status_code", None))
        return response

    def _watch_teardown(exc: Any = None) -> None:
        token = g.pop(_TOKEN, None)
        status = g.pop(_STATUS, None)
        if token is not None:
            end_request(token, 500 if exc is not None and status is None else status)

    app.before_request(_watch_before)
    app.after_request(_watch_after)
    app.teardown_request(_watch_teardown)

    def _on_exception(sender: Any, exception: BaseException, **_extra: Any) -> None:
        capture_exception(
            exception,
            context={"framework": "flask"},
            session_id=request.headers.get("X-Watch-Session"),
            url=request.path,
            method=request.method,
            status=500,
        )

    got_request_exception.connect(_on_exception, app, weak=False)
    return app
