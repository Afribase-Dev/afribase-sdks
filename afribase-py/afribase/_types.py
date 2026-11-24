"""Core type definitions for the Afribase Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

try:  # Python 3.8+: typing has these; kept in a try for type checkers on old versions
    from typing import Literal, Protocol, TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import Literal, Protocol, TypedDict  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Auth Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class UserIdentity:
    id: str
    user_id: str
    identity_data: Dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    created_at: str = ""
    updated_at: str = ""
    identity_id: Optional[str] = None
    last_sign_in_at: Optional[str] = None
    email: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserIdentity":
        """Reads the known keys and ignores the rest, so new server fields never break parsing."""
        return cls(
            id=data.get("id") or "",
            user_id=data.get("user_id") or "",
            identity_data=data.get("identity_data") or {},
            provider=data.get("provider") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            identity_id=data.get("identity_id"),
            last_sign_in_at=data.get("last_sign_in_at"),
            email=data.get("email"),
        )


@dataclass
class Factor:
    id: str
    factor_type: str = ""  # "totp" | "phone" | "webauthn"
    status: str = ""  # "verified" | "unverified"
    created_at: str = ""
    updated_at: str = ""
    friendly_name: Optional[str] = None
    phone: Optional[str] = None
    last_challenged_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Factor":
        return cls(
            id=data.get("id") or "",
            factor_type=data.get("factor_type") or "",
            status=data.get("status") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            friendly_name=data.get("friendly_name"),
            phone=data.get("phone"),
            last_challenged_at=data.get("last_challenged_at"),
        )


@dataclass
class User:
    id: str
    aud: str
    created_at: str
    app_metadata: Dict[str, Any] = field(default_factory=dict)
    user_metadata: Dict[str, Any] = field(default_factory=dict)
    email: Optional[str] = None
    phone: Optional[str] = None
    updated_at: Optional[str] = None
    is_anonymous: Optional[bool] = None
    role: Optional[str] = None
    confirmed_at: Optional[str] = None
    last_sign_in_at: Optional[str] = None
    identities: Optional[List[UserIdentity]] = None
    factors: Optional[List[Factor]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        identities = None
        if data.get("identities"):
            identities = [UserIdentity.from_dict(i) for i in data["identities"] if isinstance(i, dict)]
        factors = None
        if data.get("factors"):
            factors = [Factor.from_dict(f) for f in data["factors"] if isinstance(f, dict)]
        return cls(
            id=data.get("id", ""),
            aud=data.get("aud", ""),
            created_at=data.get("created_at", ""),
            app_metadata=data.get("app_metadata") or {},
            user_metadata=data.get("user_metadata") or {},
            email=data.get("email"),
            phone=data.get("phone"),
            updated_at=data.get("updated_at"),
            is_anonymous=data.get("is_anonymous"),
            role=data.get("role"),
            confirmed_at=data.get("confirmed_at"),
            last_sign_in_at=data.get("last_sign_in_at"),
            identities=identities,
            factors=factors,
        )


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user: User
    expires_at: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Like the JS ``_makeSession``: expires_in defaults to 3600, expires_at to now + expires_in."""
        import time

        user_data = data.get("user") or data
        user = User.from_dict(user_data) if isinstance(user_data, dict) else user_data
        expires_in = int(data.get("expires_in") or 3600)
        expires_at = data.get("expires_at") or int(time.time()) + expires_in
        return cls(
            access_token=data.get("access_token") or "",
            refresh_token=data.get("refresh_token") or "",
            expires_in=expires_in,
            token_type=data.get("token_type") or "bearer",
            user=user,
            expires_at=int(expires_at),
        )

    def to_dict(self) -> Dict[str, Any]:
        """The JSON shape the JS SDK stores under ``afribase.auth.token``."""
        from dataclasses import asdict

        return asdict(self)


class AuthChangeEvent(str, Enum):
    SIGNED_IN = "SIGNED_IN"
    SIGNED_OUT = "SIGNED_OUT"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    USER_UPDATED = "USER_UPDATED"
    PASSWORD_RECOVERY = "PASSWORD_RECOVERY"
    INITIAL_SESSION = "INITIAL_SESSION"


AuthChangeCallback = Callable[[AuthChangeEvent, Optional[Session]], None]


@dataclass
class Subscription:
    """Returned by ``on_auth_state_change``; call ``unsubscribe()`` to stop listening."""

    id: str
    unsubscribe: Callable[[], None]

    def __call__(self) -> None:  # older code called the return value directly
        self.unsubscribe()


class SupportedStorage(Protocol):
    """Where a client keeps its session between runs (file, keyring, Redis, ...).

    Same contract as the JS SDK's ``SupportedStorage``; methods may raise, errors are ignored.
    """

    def get_item(self, key: str) -> Optional[str]: ...

    def set_item(self, key: str, value: str) -> None: ...

    def remove_item(self, key: str) -> None: ...


class MemoryStorage:
    """A ``SupportedStorage`` kept in memory (handy for tests and long-running workers)."""

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def get_item(self, key: str) -> Optional[str]:
        return self._data.get(key)

    def set_item(self, key: str, value: str) -> None:
        self._data[key] = value

    def remove_item(self, key: str) -> None:
        self._data.pop(key, None)


OAuthProvider = Literal[
    "apple", "azure", "bitbucket", "discord", "facebook", "figma", "fly", "github", "gitlab", "google",
    "kakao", "keycloak", "linkedin", "linkedin_oidc", "notion", "slack", "slack_oidc", "snapchat",
    "spotify", "twitch", "twitter", "workos", "x", "zoom",
]

VerifyOtpType = Literal["sms", "email", "signup", "magiclink", "recovery"]


class UserAttributes(TypedDict, total=False):
    email: str
    phone: str
    password: str
    data: Dict[str, Any]


FilterOperator = Literal[
    "eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is", "in", "cs", "cd", "sl", "sr",
    "nxl", "nxr", "adj", "ov", "fts", "plfts", "phfts", "wfts",
]

RealtimeChannelEvent = Literal["INSERT", "UPDATE", "DELETE", "*"]


@dataclass
class AuthResponse:
    """Standard return type for auth operations."""

    session: Optional[Session] = None
    user: Optional[User] = None
    error: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Storage Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StorageBucket:
    id: str
    name: str
    public: bool
    created_at: str
    updated_at: str
    file_size_limit: Optional[int] = None
    allowed_mime_types: Optional[List[str]] = None


@dataclass
class StorageObject:
    id: str
    bucket_id: str
    name: str
    mime_type: str
    size: int
    created_at: str
    updated_at: str
    etag: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TransformOptions:
    width: Optional[int] = None
    height: Optional[int] = None
    resize: Optional[str] = None  # "cover" | "contain" | "fill"
    quality: Optional[int] = None
    format: Optional[str] = None  # "origin" | "avif" | "webp"


@dataclass
class UploadOptions:
    content_type: Optional[str] = None
    cache_control: Optional[str] = None
    upsert: bool = False


@dataclass
class SignedUrlOptions:
    download: Optional[Union[str, bool]] = None
    transform: Optional[TransformOptions] = None


# ─────────────────────────────────────────────────────────────────────────────
# Functions Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FunctionInvokeOptions:
    body: Any = None
    headers: Optional[Dict[str, str]] = None
    method: str = "POST"
    region: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Query Builder / PostgREST Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PostgrestError:
    message: str
    details: str
    hint: str
    code: str


@dataclass
class PostgrestResponse:
    data: Any = None
    error: Optional[PostgrestError] = None
    count: Optional[int] = None
    status: int = 0
    status_text: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Realtime Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RealtimePresenceEntry:
    presence_ref: str
    extra: Dict[str, Any] = field(default_factory=dict)


RealtimePresenceState = Dict[str, List[RealtimePresenceEntry]]
