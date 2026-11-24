"""Base1 Watch for Python backends: error reporting and session linking.

The backend counterpart of the JS SDK's ``initWatch`` (afribase-js 0.6.0)::

    from afribase.watch import init_watch, capture_exception

    init_watch("abw_...", "https://<api>/watch/ingest", release="1.4.0", environment="prod",
               sample_rate=1.0, user=lambda: current_user_id())

    try:
        charge(order)
    except Exception:
        capture_exception()   # reports the exception being handled
        raise

Events: ``error`` (exceptions, ``capture_error``), ``log`` (``capture_message``,
or log records at ``log_event_level``), ``http`` (outgoing ``requests``/``httpx``
calls that fail or answer >= 500) and ``slow`` (requests slower than ``slow_ms``),
each with the last 30 breadcrumbs of the request (request, fetch, console, custom).

Framework integrations capture unhandled exceptions and read the
``X-Watch-Session`` header that the Afribase mobile SDKs add to app requests,
so the dashboard links a mobile session replay to the backend error it caused:

- Django: add ``"afribase.watch.django.WatchMiddleware"`` to ``MIDDLEWARE``.
- Flask: ``from afribase.watch.flask import init_flask; init_flask(app)``.
- FastAPI / Starlette (any ASGI app):
  ``from afribase.watch.asgi import WatchMiddleware; app.add_middleware(WatchMiddleware)``.

The frameworks are optional: nothing here imports them until you use an integration.
"""

from afribase.watch._client import (
    SESSION_HEADER,
    WatchClient,
    add_breadcrumb,
    begin_request,
    capture_error,
    capture_exception,
    capture_message,
    end_request,
    flush,
    get_client,
    init_watch,
    session_from_headers,
    stop,
    strip_query,
)

__all__ = [
    "SESSION_HEADER",
    "WatchClient",
    "add_breadcrumb",
    "begin_request",
    "capture_error",
    "capture_exception",
    "capture_message",
    "end_request",
    "flush",
    "get_client",
    "init_watch",
    "session_from_headers",
    "stop",
    "strip_query",
]
