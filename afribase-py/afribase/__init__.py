"""
Afribase Python SDK
===================

The official Python client for Afribase — an open-source backend-as-a-service platform.

Usage::

    from afribase import create_client

    client = create_client("https://your-project.useafribase.app", "your-anon-key")

    # Auth
    session = client.auth.sign_in_with_password(email="user@example.com", password="secret")

    # Database (PostgREST query builder)
    data = client.from_("posts").select("*").eq("published", True).execute()

    # Storage
    client.storage.from_("avatars").upload("avatar.png", file_bytes)

    # Edge Functions
    result = client.functions.invoke("my-function", body={"foo": "bar"})

    # Realtime
    channel = client.channel("room1")
    channel.on_broadcast("message", lambda payload: print(payload))
    channel.subscribe()
"""

from afribase._client import AfribaseClient, create_client
from afribase._email import AfribaseEmailClient
from afribase.modular import (
    db, select, insert, update, upsert, delete,
    eq, neq, gt, gte, lt, lte, like, ilike, is_, in_, match,
    order, limit, single, maybe_single
)
from afribase._types import (
    AuthChangeEvent,
    Factor,
    FunctionInvokeOptions,
    PostgrestError,
    PostgrestResponse,
    Session,
    SignedUrlOptions,
    StorageBucket,
    StorageObject,
    TransformOptions,
    UploadOptions,
    User,
    UserIdentity,
)

__all__ = [
    "AfribaseClient",
    "AfribaseEmailClient",
    "create_client",
    "AuthChangeEvent",
    "Factor",
    "FunctionInvokeOptions",
    "PostgrestError",
    "PostgrestResponse",
    "Session",
    "SignedUrlOptions",
    "StorageBucket",
    "StorageObject",
    "TransformOptions",
    "UploadOptions",
    "User",
    "UserIdentity",
    "db", "select", "insert", "update", "upsert", "delete",
    "eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is_", "in_", "match",
    "order", "limit", "single", "maybe_single",
]

__version__ = "0.3.0"
