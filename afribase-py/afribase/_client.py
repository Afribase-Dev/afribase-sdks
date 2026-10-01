"""AfribaseClient — main entry point for the Afribase Python SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._auth import AfribaseAuthClient
from ._email import AfribaseEmailClient
from ._functions import AfribaseFunctionsClient
from ._query_builder import AfribaseQueryBuilder, AfribaseRpcBuilder
from ._realtime import AfribaseRealtimeClient, RealtimeChannel
from ._storage import AfribaseStorageClient


def _extract_slug(url: str) -> str:
    """Extract the project slug from the base URL for the email API path."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # Path-based: /p/:slug/...
        import re
        m = re.match(r"^/p/([^/]+)", parsed.path)
        if m:
            return m.group(1)
        # Subdomain: slug.useafribase.app
        parts = parsed.hostname.split(".") if parsed.hostname else []
        if len(parts) >= 3:
            return parts[0]
    except Exception:
        pass
    return "_"


class AfribaseClient:
    """Afribase client — your single entry point for every Afribase service.

    Usage::

        from afribase import create_client

        client = create_client("https://your-project.useafribase.app", "your-anon-key")

        # Auth
        res = client.auth.sign_up(email="a@b.com", password="secret")

        # Query builder (PostgREST)
        data = client.from_("todos").select("*").eq("done", "false").execute()

        # RPC
        result = client.rpc("my_function", {"arg": "value"}).execute()

        # Storage
        client.storage.from_("avatars").upload("me.png", file_bytes)

        # Functions
        resp = client.functions.invoke("hello", body={"name": "world"})

        # Realtime
        channel = client.channel("room1")
        channel.on_broadcast("msg", callback=lambda p: print(p))
        channel.subscribe()
    """

    def __init__(
        self,
        afribase_url: str,
        afribase_key: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        auth_url: Optional[str] = None,
        rest_url: Optional[str] = None,
        storage_url: Optional[str] = None,
        functions_url: Optional[str] = None,
        realtime_url: Optional[str] = None,
    ) -> None:
        self._url = afribase_url.rstrip("/")
        self._key = afribase_key
        self._headers = headers or {}
        self._auth_url = auth_url or f"{self._url}/auth/v1"
        self._rest_url = rest_url or f"{self._url}/rest/v1"
        self._storage_url = storage_url or f"{self._url}/storage/v1"
        self._functions_url = functions_url or f"{self._url}/functions/v1"
        self._realtime_url = realtime_url or self._url

        self._email_slug = _extract_slug(self._url)

        # Lazy-initialised service clients
        self._auth: Optional[AfribaseAuthClient] = None
        self._storage: Optional[AfribaseStorageClient] = None
        self._functions: Optional[AfribaseFunctionsClient] = None
        self._realtime: Optional[AfribaseRealtimeClient] = None
        self._email: Optional[AfribaseEmailClient] = None

    # ─── Service accessors ────────────────────────────────────────────

    @property
    def auth(self) -> AfribaseAuthClient:
        """Auth client (sign-up, sign-in, tokens, OAuth, OTP, …)."""
        if self._auth is None:
            self._auth = AfribaseAuthClient(
                url=self._auth_url,
                api_key=self._key,
                headers=self._headers,
            )
        return self._auth

    @property
    def storage(self) -> AfribaseStorageClient:
        """Storage client (buckets, upload, download, signed URLs, …)."""
        if self._storage is None:
            self._storage = AfribaseStorageClient(
                url=self._storage_url,
                api_key=self._key,
                get_access_token=lambda: self.auth.access_token,
            )
        return self._storage

    @property
    def functions(self) -> AfribaseFunctionsClient:
        """Edge Functions client (invoke remote functions)."""
        if self._functions is None:
            self._functions = AfribaseFunctionsClient(
                url=self._functions_url,
                api_key=self._key,
                get_access_token=lambda: self.auth.access_token,
            )
        return self._functions

    @property
    def email(self) -> AfribaseEmailClient:
        """Email client — send transactional emails using your configured SMTP.

        Example::

            client.email.send(
                to="user@example.com",
                template_id="welcome",
                template_vars={"name": "John"},
            )
        """
        if self._email is None:
            self._email = AfribaseEmailClient(
                url=f"{self._url}/email/v1",
                slug=self._email_slug,
                api_key=self._key,
                get_access_token=lambda: self.auth.access_token,
            )
        return self._email

    @property
    def realtime(self) -> AfribaseRealtimeClient:
        """Low-level realtime client.  Prefer ``channel()`` instead."""
        if self._realtime is None:
            self._realtime = AfribaseRealtimeClient(
                url=self._realtime_url,
                api_key=self._key,
                access_token=self.auth.access_token,
            )
        return self._realtime

    # ─── Query builder ────────────────────────────────────────────────

    def from_(self, table: str) -> AfribaseQueryBuilder:
        """Return a query builder for *table* (PostgREST)."""
        return AfribaseQueryBuilder(
            url=f"{self._rest_url}/{table}",
            api_key=self._key,
            access_token=self.auth.access_token,
        )

    def rpc(
        self,
        fn: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> AfribaseRpcBuilder:
        """Call a Postgres function via RPC."""
        return AfribaseRpcBuilder(
            rest_url=self._rest_url,
            fn=fn,
            params=params or {},
            api_key=self._key,
            access_token=self.auth.access_token,
        )

    # ─── Realtime helpers ─────────────────────────────────────────────

    def channel(self, name: str) -> RealtimeChannel:
        """Create (or get) a realtime channel."""
        return self.realtime.channel(name)

    def remove_channel(self, channel: RealtimeChannel) -> None:
        """Remove a specific realtime channel."""
        self.realtime.remove_channel(channel)

    def remove_all_channels(self) -> None:
        """Remove all realtime channels and disconnect."""
        self.realtime.remove_all_channels()

    # ─── Cleanup ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Clean up resources (disconnect realtime, etc.)."""
        if self._realtime:
            self._realtime.remove_all_channels()

    def __enter__(self) -> "AfribaseClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ─── Factory function ─────────────────────────────────────────────────


def create_client(
    afribase_url: str,
    afribase_key: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    auth_url: Optional[str] = None,
    rest_url: Optional[str] = None,
    storage_url: Optional[str] = None,
    functions_url: Optional[str] = None,
    realtime_url: Optional[str] = None,
) -> AfribaseClient:
    """Create an Afribase client.

    Args:
        afribase_url: Your project URL  (e.g. ``https://api.useafribase.app``).
        afribase_key: Your project anon/public API key.
        headers: Optional extra headers included in every request.
        auth_url: Override the auth service URL (e.g. ``https://api.useafribase.app/auth/v1/myproject``).
        rest_url: Override the REST/PostgREST URL (e.g. ``https://api.useafribase.app/rest/v1/myproject``).
        storage_url: Override the storage service URL.
        functions_url: Override the edge functions URL.
        realtime_url: Override the realtime service URL.

    Returns:
        A configured :class:`AfribaseClient` instance.
    """
    return AfribaseClient(
        afribase_url,
        afribase_key,
        headers=headers,
        auth_url=auth_url,
        rest_url=rest_url,
        storage_url=storage_url,
        functions_url=functions_url,
        realtime_url=realtime_url,
    )
