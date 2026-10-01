"""AfribaseQueryBuilder — PostgREST-compatible query builder."""

from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from afribase._http import handle_response, sync_request
from afribase._types import PostgrestError, PostgrestResponse


class AfribaseQueryBuilder:
    """Chainable PostgREST query builder matching the supabase-py / supabase-js API.

    Usage::

        # SELECT
        resp = client.from_("posts").select("*").eq("published", True).limit(10).execute()

        # INSERT
        resp = client.from_("posts").insert({"title": "Hello"}).execute()

        # UPDATE
        resp = client.from_("posts").update({"title": "Updated"}).eq("id", 1).execute()

        # DELETE
        resp = client.from_("posts").delete().eq("id", 1).execute()

        # UPSERT
        resp = client.from_("posts").upsert({"id": 1, "title": "Upserted"}).execute()
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        access_token: Optional[str] = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._access_token = access_token
        self._params: Dict[str, str] = {}
        self._headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._method: Optional[str] = None
        self._body: Any = None
        self._is_single = False
        self._is_maybe_single = False
        self._is_head = False
        self._count_type: Optional[str] = None

    # ─── CRUD ─────────────────────────────────────────────────────────

    def select(
        self,
        columns: str = "*",
        *,
        count: Optional[str] = None,
        head: bool = False,
    ) -> "AfribaseQueryBuilder":
        self._method = "GET"
        self._params["select"] = columns
        if count:
            self._count_type = count
            self._headers["Prefer"] = f"count={count}"
        if head:
            self._is_head = True
            self._method = "HEAD"
        return self

    def insert(
        self,
        values: Union[Dict[str, Any], List[Dict[str, Any]]],
        *,
        count: Optional[str] = None,
        default_to_null: bool = True,
    ) -> "AfribaseQueryBuilder":
        self._method = "POST"
        self._body = values
        prefer = ["return=representation"]
        if count:
            self._count_type = count
            prefer.append(f"count={count}")
        if not default_to_null:
            prefer.append("missing=default")
        self._headers["Prefer"] = ",".join(prefer)
        return self

    def upsert(
        self,
        values: Union[Dict[str, Any], List[Dict[str, Any]]],
        *,
        on_conflict: Optional[str] = None,
        ignore_duplicates: bool = False,
        count: Optional[str] = None,
        default_to_null: bool = True,
    ) -> "AfribaseQueryBuilder":
        self._method = "POST"
        self._body = values
        resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
        prefer = ["return=representation", f"resolution={resolution}"]
        if count:
            self._count_type = count
            prefer.append(f"count={count}")
        if not default_to_null:
            prefer.append("missing=default")
        if on_conflict:
            self._params["on_conflict"] = on_conflict
        self._headers["Prefer"] = ",".join(prefer)
        return self

    def update(
        self,
        values: Dict[str, Any],
        *,
        count: Optional[str] = None,
    ) -> "AfribaseQueryBuilder":
        self._method = "PATCH"
        self._body = values
        prefer = ["return=representation"]
        if count:
            self._count_type = count
            prefer.append(f"count={count}")
        self._headers["Prefer"] = ",".join(prefer)
        return self

    def delete(self, *, count: Optional[str] = None) -> "AfribaseQueryBuilder":
        self._method = "DELETE"
        prefer = ["return=representation"]
        if count:
            self._count_type = count
            prefer.append(f"count={count}")
        self._headers["Prefer"] = ",".join(prefer)
        return self

    # ─── Filters ──────────────────────────────────────────────────────

    def eq(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"eq.{value}"
        return self

    def neq(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"neq.{value}"
        return self

    def gt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"gt.{value}"
        return self

    def gte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"gte.{value}"
        return self

    def lt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"lt.{value}"
        return self

    def lte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"lte.{value}"
        return self

    def like(self, column: str, pattern: str) -> "AfribaseQueryBuilder":
        self._params[column] = f"like.{pattern}"
        return self

    def ilike(self, column: str, pattern: str) -> "AfribaseQueryBuilder":
        self._params[column] = f"ilike.{pattern}"
        return self

    def is_(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"is.{value}"
        return self

    def in_(self, column: str, values: List[Any]) -> "AfribaseQueryBuilder":
        cleaned = ",".join(
            f'"{v}"' if isinstance(v, str) else str(v) for v in values
        )
        self._params[column] = f"in.({cleaned})"
        return self

    def contains(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        if isinstance(value, list):
            self._params[column] = f"cs.{{{','.join(str(v) for v in value)}}}"
        elif isinstance(value, dict):
            self._params[column] = f"cs.{_json.dumps(value)}"
        else:
            self._params[column] = f"cs.{value}"
        return self

    def contained_by(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        if isinstance(value, list):
            self._params[column] = f"cd.{{{','.join(str(v) for v in value)}}}"
        elif isinstance(value, dict):
            self._params[column] = f"cd.{_json.dumps(value)}"
        else:
            self._params[column] = f"cd.{value}"
        return self

    def range_gt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"sr.{value}"
        return self

    def range_gte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"nxl.{value}"
        return self

    def range_lt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"sl.{value}"
        return self

    def range_lte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"nxr.{value}"
        return self

    def range_adjacent(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"adj.{value}"
        return self

    def overlaps(self, column: str, value: List[Any]) -> "AfribaseQueryBuilder":
        self._params[column] = f"ov.{{{','.join(str(v) for v in value)}}}"
        return self

    def text_search(
        self,
        column: str,
        query: str,
        *,
        type: str = "plain",
        config: Optional[str] = None,
    ) -> "AfribaseQueryBuilder":
        prefix_map = {"plain": "plfts", "phrase": "phfts", "websearch": "wfts"}
        prefix = prefix_map.get(type, "fts")
        cfg = f"({config})" if config else ""
        self._params[column] = f"{prefix}{cfg}.{query}"
        return self

    def match(self, query: Dict[str, Any]) -> "AfribaseQueryBuilder":
        for col, val in query.items():
            self._params[col] = f"eq.{val}"
        return self

    def not_(self, column: str, operator: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"not.{operator}.{value}"
        return self

    def or_(self, filters: str, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.or" if foreign_table else "or"
        self._params[key] = f"({filters})"
        return self

    def filter(self, column: str, operator: str, value: Any) -> "AfribaseQueryBuilder":
        self._params[column] = f"{operator}.{value}"
        return self

    # ─── Modifiers ────────────────────────────────────────────────────

    def order(
        self,
        column: str,
        *,
        desc: bool = False,
        ascending: bool = True,
        null_first: bool = False,
        foreign_table: Optional[str] = None,
    ) -> "AfribaseQueryBuilder":
        direction = "desc" if desc or not ascending else "asc"
        nulls = "nullsfirst" if null_first else "nullslast"
        key = f"{foreign_table}.order" if foreign_table else "order"
        self._params[key] = f"{column}.{direction}.{nulls}"
        return self

    def limit(self, count: int, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.limit" if foreign_table else "limit"
        self._params[key] = str(count)
        return self

    def range(self, start: int, end: int, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.offset" if foreign_table else "offset"
        self._params[key] = str(start)
        limit_key = f"{foreign_table}.limit" if foreign_table else "limit"
        self._params[limit_key] = str(end - start + 1)
        return self

    def single(self) -> "AfribaseQueryBuilder":
        self._is_single = True
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def maybe_single(self) -> "AfribaseQueryBuilder":
        self._is_maybe_single = True
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def csv(self) -> "AfribaseQueryBuilder":
        self._headers["Accept"] = "text/csv"
        return self

    # ─── Execute ──────────────────────────────────────────────────────

    def execute(self) -> PostgrestResponse:
        """Execute the query and return a PostgrestResponse."""
        if not self._method:
            self._method = "GET"

        qs = "&".join(f"{k}={v}" for k, v in self._params.items())
        url = f"{self._url}?{qs}" if qs else self._url

        resp = sync_request(
            url,
            method=self._method,
            api_key=self._api_key,
            access_token=self._access_token,
            headers=self._headers,
            json=self._body,
        )

        result = handle_response(resp)

        count_val: Optional[int] = None
        content_range = resp.headers.get("content-range", "")
        if content_range and "/" in content_range:
            try:
                count_val = int(content_range.split("/")[-1])
            except (ValueError, IndexError):
                pass

        error = None
        if result["error"]:
            err = result["error"]
            error = PostgrestError(
                message=err.get("message", ""),
                details=err.get("details", ""),
                hint=err.get("hint", ""),
                code=err.get("code", ""),
            )

        return PostgrestResponse(
            data=result["data"],
            error=error,
            count=count_val,
            status=resp.status_code,
            status_text=resp.reason_phrase if hasattr(resp, "reason_phrase") else "",
        )


class AfribaseRpcBuilder:
    """Call a Postgres function (RPC)."""

    def __init__(
        self,
        rest_url: str,
        fn: str,
        params: Dict[str, Any],
        api_key: str,
        access_token: Optional[str] = None,
        *,
        head: bool = False,
        count: Optional[str] = None,
        get: bool = False,
    ) -> None:
        self._url = f"{rest_url}/rpc/{fn}"
        self._params = params
        self._api_key = api_key
        self._access_token = access_token
        self._head = head
        self._count = count
        self._get = get

    def execute(self) -> PostgrestResponse:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._count:
            headers["Prefer"] = f"count={self._count}"

        if self._get or self._head:
            method = "HEAD" if self._head else "GET"
            qs = "&".join(f"{k}={v}" for k, v in self._params.items())
            url = f"{self._url}?{qs}" if qs else self._url
            resp = sync_request(
                url,
                method=method,
                api_key=self._api_key,
                access_token=self._access_token,
                headers=headers,
            )
        else:
            resp = sync_request(
                self._url,
                method="POST",
                api_key=self._api_key,
                access_token=self._access_token,
                headers=headers,
                json=self._params,
            )

        result = handle_response(resp)
        error = None
        if result["error"]:
            err = result["error"]
            error = PostgrestError(
                message=err.get("message", ""),
                details=err.get("details", ""),
                hint=err.get("hint", ""),
                code=err.get("code", ""),
            )
        return PostgrestResponse(
            data=result["data"],
            error=error,
            status=resp.status_code,
            status_text=resp.reason_phrase if hasattr(resp, "reason_phrase") else "",
        )
