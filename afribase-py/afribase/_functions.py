"""AfribaseFunctionsClient — invoke Afribase Edge Functions."""

from __future__ import annotations

import json as _json
from typing import Any, Dict, Optional

from afribase._http import handle_response, sync_request
from afribase._types import FunctionInvokeOptions


class AfribaseFunctionsClient:
    """Invoke Afribase Edge Functions.

    Usage::

        result = client.functions.invoke("my-function", body={"foo": "bar"})
        print(result["data"])
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        get_access_token: Any,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._get_token = get_access_token

    def invoke(
        self,
        function_name: str,
        *,
        body: Any = None,
        headers: Optional[Dict[str, str]] = None,
        method: str = "POST",
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke an Edge Function by name.

        Args:
            function_name: The function slug/name.
            body: The request body (will be JSON-encoded if dict/list).
            headers: Additional headers.
            method: HTTP method (default POST).
            region: Optional region hint.

        Returns:
            Dict with "data" and "error" keys.
        """
        url = f"{self._url}/{function_name}"
        if region:
            url += f"?region={region}"

        extra_headers: Dict[str, str] = {}
        if headers:
            extra_headers.update(headers)

        json_body = None
        raw_body = None
        if body is not None:
            if isinstance(body, (dict, list)):
                json_body = body
                extra_headers.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                raw_body = body.encode("utf-8")
                extra_headers.setdefault("Content-Type", "text/plain")
            elif isinstance(body, bytes):
                raw_body = body
                extra_headers.setdefault("Content-Type", "application/octet-stream")

        resp = sync_request(
            url,
            method=method,
            api_key=self._api_key,
            access_token=self._get_token(),
            headers=extra_headers,
            json=json_body,
            body=raw_body,
        )

        if resp.status_code >= 400:
            result = handle_response(resp)
            return {"data": None, "error": result["error"]}

        # Try to parse as JSON
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
        else:
            data = resp.text

        return {"data": data, "error": None}
