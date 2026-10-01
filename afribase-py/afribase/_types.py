"""Core type definitions for the Afribase Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


# ─────────────────────────────────────────────────────────────────────────────
# Auth Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class UserIdentity:
    id: str
    user_id: str
    identity_data: Dict[str, Any]
    provider: str
    created_at: str
    updated_at: str


@dataclass
class Factor:
    id: str
    factor_type: str  # "totp" | "phone" | "webauthn"
    status: str  # "verified" | "unverified"
    created_at: str
    updated_at: str
    friendly_name: Optional[str] = None


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
            identities = [
                UserIdentity(**i) for i in data["identities"]
            ]
        factors = None
        if data.get("factors"):
            factors = [Factor(**f) for f in data["factors"]]
        return cls(
            id=data.get("id", ""),
            aud=data.get("aud", ""),
            created_at=data.get("created_at", ""),
            app_metadata=data.get("app_metadata", {}),
            user_metadata=data.get("user_metadata", {}),
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
        user_data = data.get("user", data)
        user = User.from_dict(user_data) if isinstance(user_data, dict) else user_data
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_in=data.get("expires_in", 0),
            token_type=data.get("token_type", "bearer"),
            user=user,
            expires_at=data.get("expires_at"),
        )


class AuthChangeEvent(str, Enum):
    SIGNED_IN = "SIGNED_IN"
    SIGNED_OUT = "SIGNED_OUT"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    USER_UPDATED = "USER_UPDATED"
    PASSWORD_RECOVERY = "PASSWORD_RECOVERY"
    INITIAL_SESSION = "INITIAL_SESSION"


AuthChangeCallback = Callable[[AuthChangeEvent, Optional[Session]], None]


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
