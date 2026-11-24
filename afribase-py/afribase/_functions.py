"""AfribaseFunctionsClient — invoke Afribase Edge Functions."""

from __future__ import annotations

import json as _json
from typing import Any, Dict, Optional

from afribase._http import HeadersMixin, handle_response
from afribase._types import FunctionInvokeOptions


class AfribaseFunctionsClient(HeadersMixin):
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

        extra_headers: Dict[str, str] = {}
        if headers:
            extra_headers.update(headers)
        if region:
            extra_headers["x-region"] = region  # like JS; was a ?region= query param
        has_ctype = any(k.lower() == "content-type" for k in extra_headers)

        def default_ctype(value: str) -> None:
            if not has_ctype:
                extra_headers["Content-Type"] = value

        json_body = None
        raw_body = None
        if body is not None:
            if isinstance(body, str):
                raw_body = body.encode("utf-8")
                default_ctype("text/plain")
            elif isinstance(body, (bytes, bytearray)):
                raw_body = bytes(body)
                default_ctype("application/octet-stream")
            else:
                # Everything else (dicts, lists, numbers, booleans, ...) is JSON, like JS.
                raw_body = _json.dumps(body, default=str).encode("utf-8")
                default_ctype("application/json")

        resp = self._sync(
            url,
            method=method,
            api_key=self._api_key,
            access_token=self._get_token(),
            headers=extra_headers,
            json=json_body,
            body=raw_body,
        )

        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            result = handle_response(resp)
            return {"data": result["data"], "error": result["error"]}
        if resp.status_code >= 400:
            return {"data": None, "error": {"message": resp.text, "status": resp.status_code}}
        return {"data": resp.text, "error": None}
