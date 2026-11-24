"""Django integration: add ``"afribase.watch.django.WatchMiddleware"`` to MIDDLEWARE.

Reports exceptions a view raises (Django calls ``process_exception`` for
unhandled view exceptions) with the request's path, method, breadcrumbs and
``X-Watch-Session`` header, and requests slower than ``slow_ms`` as ``slow``. Django itself is not imported here.
"""

from __future__ import annotations

from typing import Any, Callable

from afribase.watch._client import begin_request, capture_exception, end_request


class WatchMiddleware:
    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        token = begin_request(_session(request), _path(request), getattr(request, "method", None))
        status = None
        try:
            response = self.get_response(request)
            status = getattr(response, "status_code", None)
            return response
        finally:
            end_request(token, status)

    def process_exception(self, request: Any, exception: BaseException) -> None:
        if _is_client_error(exception):
            return None  # 404 / 403 / 400: Django answers these, not a crash
        capture_exception(exception, context={"framework": "django"}, status=500)
        return None  # let Django's normal error handling run


def _is_client_error(exc: BaseException) -> bool:
    try:
        from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
        from django.http import Http404
    except ImportError:  # very old Django: no BadRequest
        try:
            from django.core.exceptions import PermissionDenied, SuspiciousOperation
            from django.http import Http404
        except ImportError:
            return False
        return isinstance(exc, (Http404, PermissionDenied, SuspiciousOperation))
    return isinstance(exc, (Http404, PermissionDenied, SuspiciousOperation, BadRequest))


def _session(request: Any) -> Any:
    meta = getattr(request, "META", None) or {}
    v = meta.get("HTTP_X_WATCH_SESSION")
    if v is None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            v = headers.get("X-Watch-Session")
    return v


def _path(request: Any) -> Any:
    return getattr(request, "path", None)
