"""AfribaseQueryBuilder — PostgREST-compatible query builder (parity with the JS SDK)."""

from __future__ import annotations

import json as _json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote, urlencode

from afribase._http import HeadersMixin, error_body
from afribase._types import PostgrestError, PostgrestResponse

# Characters PostgREST syntax needs left readable; everything else is percent-encoded.
_SAFE = ",.()*:"


def _fmt(v: Any) -> str:
    """A filter value as PostgREST expects it: None -> null, True -> true."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _qs(pairs: List[Tuple[str, str]]) -> str:
    return urlencode(pairs, quote_via=quote, safe=_SAFE)


def _postgrest_error(resp: Any, fallback: str) -> PostgrestError:
    body = error_body(resp, fallback)
    return PostgrestError(
        message=body.get("message") or body.get("msg") or fallback,
        details=body.get("details") or "",
        hint=body.get("hint") or "",
        code=str(body.get("code") or resp.status_code),
    )


def _parse_body(resp: Any) -> Any:
    """JSON, or raw text for csv / geojson / explain plans (like JS)."""
    if resp.status_code == 204 or not resp.content:
        return None
    ctype = resp.headers.get("content-type", "")
    if "text/csv" in ctype or "geo+json" in ctype or "pgrst.plan" in ctype:
        return resp.text
    try:
        return resp.json()
    except Exception:
        return resp.text


def _count(resp: Any) -> Optional[int]:
    m = re.search(r"/(\d+)", resp.headers.get("content-range", ""))
    return int(m.group(1)) if m else None


class AfribaseQueryBuilder(HeadersMixin):
    """Chainable PostgREST query builder matching the supabase-py / supabase-js API.

    Usage::

        resp = client.from_("posts").select("*").eq("published", True).limit(10).execute()
        resp = client.from_("posts").insert({"title": "Hello"}).execute()
        resp = client.from_("posts").update({"title": "Updated"}).eq("id", 1).execute()
        resp = client.from_("posts").delete().eq("id", 1).execute()
        resp = client.from_("posts").upsert({"id": 1, "title": "Upserted"}).execute()

    Filters on the same column add up (``.gte("age", 18).lte("age", 65)``), like JS.
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
        self._params: List[Tuple[str, str]] = []
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

    # ─── query string helpers ─────────────────────────────────────────

    def _append(self, key: str, value: str) -> "AfribaseQueryBuilder":
        self._params.append((key, value))
        return self

    def _set(self, key: str, value: str) -> "AfribaseQueryBuilder":
        self._params = [(k, v) for k, v in self._params if k != key]
        self._params.append((key, value))
        return self

    # ─── CRUD ─────────────────────────────────────────────────────────

    def select(
        self,
        columns: str = "*",
        *,
        count: Optional[str] = None,
        head: bool = False,
    ) -> "AfribaseQueryBuilder":
        self._method = "GET"
        self._set("select", columns)
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
            self._set("on_conflict", on_conflict)
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
        return self._append(column, f"eq.{_fmt(value)}")

    def neq(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"neq.{_fmt(value)}")

    def gt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"gt.{_fmt(value)}")

    def gte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"gte.{_fmt(value)}")

    def lt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"lt.{_fmt(value)}")

    def lte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"lte.{_fmt(value)}")

    def like(self, column: str, pattern: str) -> "AfribaseQueryBuilder":
        return self._append(column, f"like.{pattern}")

    def ilike(self, column: str, pattern: str) -> "AfribaseQueryBuilder":
        return self._append(column, f"ilike.{pattern}")

    def is_(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"is.{_fmt(value)}")

    def in_(self, column: str, values: List[Any]) -> "AfribaseQueryBuilder":
        cleaned = ",".join(f'"{v}"' if isinstance(v, str) else _fmt(v) for v in values)
        return self._append(column, f"in.({cleaned})")

    def _containment(self, op: str, column: str, value: Any) -> "AfribaseQueryBuilder":
        if isinstance(value, list):
            return self._append(column, f"{op}.{{{','.join(_fmt(v) for v in value)}}}")
        if isinstance(value, dict):
            return self._append(column, f"{op}.{_json.dumps(value, separators=(',', ':'))}")
        return self._append(column, f"{op}.{_fmt(value)}")

    def contains(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._containment("cs", column, value)

    def contained_by(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._containment("cd", column, value)

    def range_gt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"sr.{value}")

    def range_gte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"nxl.{value}")

    def range_lt(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"sl.{value}")

    def range_lte(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"nxr.{value}")

    def range_adjacent(self, column: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"adj.{value}")

    def overlaps(self, column: str, value: List[Any]) -> "AfribaseQueryBuilder":
        return self._append(column, f"ov.{{{','.join(_fmt(v) for v in value)}}}")

    def text_search(
        self,
        column: str,
        query: str,
        *,
        type: Optional[str] = None,
        config: Optional[str] = None,
    ) -> "AfribaseQueryBuilder":
        """Full-text search: no type -> ``fts``; plain / phrase / websearch -> plfts / phfts / wfts."""
        prefix = {"plain": "plfts", "phrase": "phfts", "websearch": "wfts"}.get(type or "", "fts")
        cfg = f"({config})" if config else ""
        return self._append(column, f"{prefix}{cfg}.{query}")

    def match(self, query: Dict[str, Any]) -> "AfribaseQueryBuilder":
        for col, val in query.items():
            self._append(col, f"eq.{_fmt(val)}")
        return self

    def not_(self, column: str, operator: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"not.{operator}.{_fmt(value)}")

    def or_(self, filters: str, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.or" if foreign_table else "or"
        return self._append(key, f"({filters})")

    def filter(self, column: str, operator: str, value: Any) -> "AfribaseQueryBuilder":
        return self._append(column, f"{operator}.{_fmt(value)}")

    # ─── Modifiers ────────────────────────────────────────────────────

    def order(
        self,
        column: str,
        *,
        desc: bool = False,
        ascending: bool = True,
        nulls_first: bool = False,
        foreign_table: Optional[str] = None,
        null_first: Optional[bool] = None,
    ) -> "AfribaseQueryBuilder":
        """Orders results; several calls add up. ``null_first`` is the old name of ``nulls_first``."""
        if null_first is not None:
            nulls_first = null_first
        direction = "desc" if desc or not ascending else "asc"
        nulls = "nullsfirst" if nulls_first else "nullslast"
        key = f"{foreign_table}.order" if foreign_table else "order"
        return self._append(key, f"{column}.{direction}.{nulls}")

    def limit(self, count: int, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.limit" if foreign_table else "limit"
        return self._set(key, str(count))

    def range(self, start: int, end: int, *, foreign_table: Optional[str] = None) -> "AfribaseQueryBuilder":
        key = f"{foreign_table}.offset" if foreign_table else "offset"
        self._set(key, str(start))
        limit_key = f"{foreign_table}.limit" if foreign_table else "limit"
        self._set(limit_key, str(end - start + 1))
        self._headers["Range"] = f"{start}-{end}"
        self._headers["Range-Unit"] = "items"
        return self

    def single(self) -> "AfribaseQueryBuilder":
        self._is_single = True
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def maybe_single(self) -> "AfribaseQueryBuilder":
        """Like ``single()``, but no row gives ``data=None`` without an error."""
        self._is_maybe_single = True
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def csv(self) -> "AfribaseQueryBuilder":
        self._headers["Accept"] = "text/csv"
        return self

    def geojson(self) -> "AfribaseQueryBuilder":
        """Return the rows as a GeoJSON string."""
        self._headers["Accept"] = "application/geo+json"
        return self

    def explain(
        self,
        *,
        analyze: bool = False,
        verbose: bool = False,
        settings: bool = False,
        buffers: bool = False,
        format: Optional[str] = None,
    ) -> "AfribaseQueryBuilder":
        """Return the query plan (text) instead of rows; ``format`` is "json" or "text"."""
        parts = ["application/vnd.pgrst.plan"]
        for flag, name in ((analyze, "analyze"), (verbose, "verbose"), (settings, "settings"), (buffers, "buffers")):
            if flag:
                parts.append(name)
        if format:
            parts.append(format)
        self._headers["Accept"] = "+".join(parts)
        return self

    # ─── Execute ──────────────────────────────────────────────────────

    def execute(self) -> PostgrestResponse:
        """Execute the query and return a PostgrestResponse."""
        if not self._method:
            self._method = "GET"

        qs = _qs(self._params)
        url = f"{self._url}?{qs}" if qs else self._url

        resp = self._sync(
            url,
            method=self._method,
            api_key=self._api_key,
            access_token=self._access_token,
            headers=self._headers,
            json=self._body,
        )
        status_text = getattr(resp, "reason_phrase", "") or ""
        count_val = _count(resp) if self._count_type else None

        if resp.status_code >= 400:
            err = _postgrest_error(resp, f"Request failed with status {resp.status_code}")
            if self._is_maybe_single and resp.status_code == 406 and err.code == "PGRST116":
                return PostgrestResponse(data=None, error=None, count=count_val, status=200, status_text="OK")
            return PostgrestResponse(data=None, error=err, count=count_val, status=resp.status_code, status_text=status_text)

        return PostgrestResponse(
            data=None if self._is_head else _parse_body(resp),
            error=None,
            count=count_val,
            status=resp.status_code,
            status_text=status_text,
        )


class AfribaseRpcBuilder(HeadersMixin):
    """Call a Postgres function (RPC), with the JS builder's chain methods."""

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
        self._query: List[Tuple[str, str]] = []
        self._headers: Dict[str, str] = {"Content-Type": "application/json", "Prefer": "return=representation"}
        if count:
            self._headers["Prefer"] = f"count={count}"

    def _set(self, key: str, value: str) -> "AfribaseRpcBuilder":
        self._query = [(k, v) for k, v in self._query if k != key]
        self._query.append((key, value))
        return self

    def select(self, columns: str = "*") -> "AfribaseRpcBuilder":
        return self._set("select", columns)

    def order(self, column: str, *, ascending: bool = True) -> "AfribaseRpcBuilder":
        self._query.append(("order", f"{column}.{'asc' if ascending else 'desc'}"))
        return self

    def limit(self, count: int) -> "AfribaseRpcBuilder":
        return self._set("limit", str(count))

    def range(self, start: int, end: int) -> "AfribaseRpcBuilder":
        self._set("offset", str(start))
        self._set("limit", str(end - start + 1))
        self._headers["Range"] = f"{start}-{end}"
        self._headers["Range-Unit"] = "items"
        return self

    def eq(self, column: str, value: Any) -> "AfribaseRpcBuilder":
        self._query.append((column, f"eq.{_fmt(value)}"))
        return self

    def filter(self, column: str, operator: str, value: Any) -> "AfribaseRpcBuilder":
        self._query.append((column, f"{operator}.{_fmt(value)}"))
        return self

    def single(self) -> "AfribaseRpcBuilder":
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def maybe_single(self) -> "AfribaseRpcBuilder":
        self._headers["Accept"] = "application/vnd.pgrst.object+json"
        return self

    def execute(self) -> PostgrestResponse:
        query = list(self._query)
        if self._get or self._head:
            method = "HEAD" if self._head else "GET"
            query = [(k, _fmt(v)) for k, v in self._params.items()] + query
            body = None
        else:
            method = "POST"
            body = self._params
        qs = _qs(query)
        url = f"{self._url}?{qs}" if qs else self._url
        resp = self._sync(
            url,
            method=method,
            api_key=self._api_key,
            access_token=self._access_token,
            headers=self._headers,
            json=body,
        )
        status_text = getattr(resp, "reason_phrase", "") or ""
        count_val = _count(resp) if self._count else None
        if resp.status_code >= 400:
            return PostgrestResponse(
                data=None, error=_postgrest_error(resp, f"RPC failed with status {resp.status_code}"),
                count=count_val, status=resp.status_code, status_text=status_text,
            )
        return PostgrestResponse(
            data=None if self._head else _parse_body(resp),
            error=None, count=count_val, status=resp.status_code, status_text=status_text,
        )
