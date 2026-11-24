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

from afribase._auth import AfribaseAuthClient
from afribase._client import AfribaseClient, create_client
from afribase._email import AfribaseEmailClient
from afribase._functions import AfribaseFunctionsClient
from afribase._query_builder import AfribaseQueryBuilder, AfribaseRpcBuilder
from afribase._realtime import AfribaseRealtimeClient, RealtimeChannel
from afribase._storage import AfribaseStorageClient, StorageFileApi
from afribase.modular import (
    db, select, insert, update, upsert, delete,
    eq, neq, gt, gte, lt, lte, like, ilike, is_, in_, match,
    contains, contained_by, text_search, not_, or_, filter,
    order, limit, range, single, maybe_single, csv, geojson, explain,
)
from afribase._types import (
    AuthChangeCallback,
    AuthChangeEvent,
    AuthResponse,
    Factor,
    FilterOperator,
    MemoryStorage,
    OAuthProvider,
    RealtimeChannelEvent,
    Subscription,
    SupportedStorage,
    UserAttributes,
    VerifyOtpType,
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
    "AfribaseAuthClient",
    "AfribaseClient",
    "AfribaseEmailClient",
    "AfribaseFunctionsClient",
    "AfribaseQueryBuilder",
    "AfribaseRealtimeClient",
    "AfribaseRpcBuilder",
    "AfribaseStorageClient",
    "RealtimeChannel",
    "StorageFileApi",
    "create_client",
    "AuthChangeCallback",
    "AuthChangeEvent",
    "AuthResponse",
    "FilterOperator",
    "MemoryStorage",
    "OAuthProvider",
    "RealtimeChannelEvent",
    "Subscription",
    "SupportedStorage",
    "UserAttributes",
    "VerifyOtpType",
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
    "contains", "contained_by", "text_search", "not_", "or_",
    "order", "limit", "single", "maybe_single", "csv", "geojson", "explain",
    # range and filter stay importable by name but out of __all__, so "import *" keeps the builtins.
]

__version__ = "0.4.0"
