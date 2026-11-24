"""Shared HTTP helpers wrapping httpx."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

DEFAULT_TIMEOUT = 30.0


def _build_headers(
    api_key: str,
    access_token: Optional[str] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    # Like the JS fetch helper: apikey first, caller headers, Authorization last
    # (a caller header cannot replace the bearer token).
    headers: Dict[str, str] = {"apikey": api_key}
    if extra:
        headers.update(extra)
    headers["Authorization"] = f"Bearer {access_token or api_key}"
    return headers


async def async_request(
    url: str,
    *,
    method: str = "GET",
    api_key: str,
    access_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Any = None,
    body: Any = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """Make an authenticated async HTTP request."""
    merged = _build_headers(api_key, access_token, headers)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.request(
            method,
            url,
            headers=merged,
            json=json if body is None else None,
            content=body if body is not None else None,
        )


def sync_request(
    url: str,
    *,
    method: str = "GET",
    api_key: str,
    access_token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Any = None,
    body: Any = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """Make an authenticated sync HTTP request."""
    merged = _build_headers(api_key, access_token, headers)
    with httpx.Client(timeout=timeout) as client:
        return client.request(
            method,
            url,
            headers=merged,
            json=json if body is None else None,
            content=body if body is not None else None,
        )


def error_body(resp: httpx.Response, fallback: Optional[str] = None) -> Dict[str, Any]:
    """The error body as a dict: parsed JSON object, else ``{"message": text or fallback}``."""
    fallback = fallback or f"Request failed with status {resp.status_code}"
    try:
        body = resp.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        text = resp.text if body is None else (body if isinstance(body, str) else "")
        body = {"message": text or fallback}
    return body


def normalize_error(resp: httpx.Response, fallback: Optional[str] = None) -> Dict[str, Any]:
    """Like JS ``handleResponse``: ``{**body, message: body.message || body.msg || fallback, status}``."""
    fallback = fallback or f"Request failed with status {resp.status_code}"
    body = error_body(resp, fallback)
    err = dict(body)
    err["message"] = body.get("message") or body.get("msg") or fallback
    err["status"] = resp.status_code
    return err


def handle_response(resp: httpx.Response) -> Dict[str, Any]:
    """Parse a JSON response into {data, error} dict."""
    if resp.status_code >= 400:
        return {"data": None, "error": normalize_error(resp), "status": resp.status_code}

    if resp.status_code == 204 or not resp.content:
        return {"data": None, "error": None, "status": resp.status_code}

    try:
        data = resp.json()
    except Exception:
        data = resp.text
    return {"data": data, "error": None, "status": resp.status_code}


class HeadersMixin:
    """Merges the client's ``headers=`` option into every request a service makes."""

    _default_headers: Dict[str, str] = {}

    def _sync(self, url: str, **kw: Any) -> httpx.Response:
        if self._default_headers:
            merged = dict(self._default_headers)
            merged.update(kw.get("headers") or {})
            kw["headers"] = merged
        return sync_request(url, **kw)
