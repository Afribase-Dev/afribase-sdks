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
    headers: Dict[str, str] = {
        "apikey": api_key,
        "Authorization": f"Bearer {access_token or api_key}",
    }
    if extra:
        headers.update(extra)
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


def handle_response(resp: httpx.Response) -> Dict[str, Any]:
    """Parse a JSON response into {data, error} dict."""
    if resp.status_code >= 400:
        try:
            err = resp.json()
        except Exception:
            err = {"message": resp.text, "code": str(resp.status_code)}
        return {"data": None, "error": err, "status": resp.status_code}

    if resp.status_code == 204 or not resp.content:
        return {"data": None, "error": None, "status": resp.status_code}

    try:
        data = resp.json()
    except Exception:
        data = resp.text
    return {"data": data, "error": None, "status": resp.status_code}
