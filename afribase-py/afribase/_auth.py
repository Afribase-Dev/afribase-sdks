"""AfribaseAuthClient — authentication and user management."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

from afribase._http import handle_response, sync_request
from afribase._types import (
    AuthChangeCallback,
    AuthChangeEvent,
    AuthResponse,
    Session,
    Subscription,
    SupportedStorage,
    User,
)

STORAGE_KEY = "afribase.auth.token"
REFRESH_MARGIN = 60  # seconds before expiry, like the JS SDK


class _AdminApi:
    """``auth.admin``: administrative calls that need the service key."""

    def __init__(self, auth: "AfribaseAuthClient") -> None:
        self._auth = auth

    def delete_user(self, user_id: str, *, should_soft_delete: bool = False) -> Dict[str, Any]:
        return self._auth.delete_user(user_id, should_soft_delete=should_soft_delete)


class AfribaseAuthClient:
    """Handles sign-up, sign-in, OAuth, OTP, session management, and token refresh.

    Usage::

        auth = client.auth
        resp = auth.sign_in_with_password(email="user@example.com", password="secret")
        print(resp.session.access_token)
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        auto_refresh_token: bool = True,
        persist_session: bool = True,
        storage: Optional[SupportedStorage] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """``persist_session=False`` is stateless mode (JS ``persistSession: false``): no session is
        kept, saved or refreshed, so one server-side client never carries a user's session into
        another request. ``storage`` keeps the session between runs (JS ``storage``)."""
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._auto_refresh = auto_refresh_token
        self._persist = persist_session
        self._storage = storage
        self._headers = headers or {}
        self._session: Optional[Session] = None
        self._listeners: Dict[str, AuthChangeCallback] = {}
        self._listener_counter = 0
        self._refresh_timer: Optional[threading.Timer] = None
        self._init_lock = threading.Lock()
        self._initialized: Optional[AuthResponse] = None

    def _req(self, path: str, **kw: Any) -> Any:
        headers = dict(self._headers)
        headers.update(kw.pop("headers", None) or {})
        return sync_request(f"{self._url}{path}", api_key=self._api_key, headers=headers or None, **kw)

    # ─── Properties ───────────────────────────────────────────────────

    @property
    def access_token(self) -> Optional[str]:
        return self._session.access_token if self._session else None

    @property
    def current_session(self) -> Optional[Session]:
        return self._session

    @property
    def current_user(self) -> Optional[User]:
        return self._session.user if self._session else None

    @property
    def admin(self) -> _AdminApi:
        """Administrative API (JS ``auth.admin``); the client must use the service key."""
        return _AdminApi(self)

    # ─── Session ──────────────────────────────────────────────────────

    def initialize(self) -> AuthResponse:
        """Loads the stored session once (refreshing it when expired) and emits ``INITIAL_SESSION``.

        Runs at most once per client; ``get_session`` and ``get_user`` call it first.
        """
        with self._init_lock:
            if self._initialized is not None:
                return self._initialized
            result = AuthResponse()
            stored = self._load_stored()
            if stored is not None:
                if stored.expires_at is not None and stored.expires_at <= int(time.time()):
                    refreshed = self._refresh_with(stored.refresh_token)
                    if refreshed.error or refreshed.session is None:
                        self._remove_stored()
                        result = AuthResponse(error=refreshed.error)
                    else:
                        result = AuthResponse(session=refreshed.session, user=refreshed.session.user)
                else:
                    self._set_session(stored)
                    result = AuthResponse(session=stored, user=stored.user)
            self._initialized = result
        self._notify("INITIAL_SESSION", result.session)
        return result

    def get_session(self) -> AuthResponse:
        """Return the current session."""
        self.initialize()
        return AuthResponse(session=self._session)

    def get_user(self, jwt: Optional[str] = None) -> AuthResponse:
        """Fetch the user from the server.

        With ``jwt`` (e.g. the bearer token of an incoming request) the user is looked up for that
        token and the client's own session is left alone, so a server can verify callers
        statelessly. Without it, the current session's token is used.
        """
        if jwt is None:
            self.initialize()
        token = jwt or (self._session.access_token if self._session else None)
        if not token:
            return AuthResponse(error={"message": "Not authenticated"})
        resp = self._req("/user", access_token=token)
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        user = User.from_dict(result["data"] or {})
        if jwt is None and self._session:
            self._session.user = user
            self._save()
        return AuthResponse(user=user, session=self._session if jwt is None else None)

    def set_session(self, access_token: str, refresh_token: str) -> AuthResponse:
        """Manually set a session from existing tokens."""
        resp = self._req("/user", access_token=access_token)
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        user = User.from_dict(result["data"] or {})
        session = Session(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600,
            token_type="bearer",
            user=user,
            expires_at=int(time.time()) + 3600,
        )
        self._set_session(session)
        self._notify("SIGNED_IN", session)
        return AuthResponse(session=session, user=user)

    # ─── Sign Up / Sign In ───────────────────────────────────────────

    def sign_up(
        self,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        password: str,
        data: Optional[Dict[str, Any]] = None,
        captcha_token: Optional[str] = None,
    ) -> AuthResponse:
        """Create a new user with email/phone and password."""
        body: Dict[str, Any] = {"password": password}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if data:
            body["data"] = data
        if captcha_token:
            body["gotcha"] = captcha_token

        resp = self._req(
            "/signup",
            method="POST",
            json=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        d = result["data"]
        if d.get("access_token"):
            session = Session.from_dict(d)
            self._set_session(session)
            self._notify("SIGNED_IN", session)
            return AuthResponse(session=session, user=session.user)
        # Confirmation required
        return AuthResponse(user=User.from_dict(d))

    def sign_in_with_password(
        self,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        password: str,
        captcha_token: Optional[str] = None,
    ) -> AuthResponse:
        """Sign in with email/phone and password."""
        body: Dict[str, Any] = {"password": password}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if captcha_token:
            body["gotcha"] = captcha_token

        resp = self._req(
            "/token?grant_type=password",
            method="POST",
            json=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        session = Session.from_dict(result["data"])
        self._set_session(session)
        self._notify("SIGNED_IN", session)
        return AuthResponse(session=session, user=session.user)

    def sign_in_with_oauth(
        self,
        *,
        provider: str,
        redirect_to: Optional[str] = None,
        scopes: Optional[str] = None,
        query_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Build an OAuth redirect URL for a third-party provider."""
        params: Dict[str, str] = {"provider": provider}
        if redirect_to:
            params["redirect_to"] = redirect_to
        if scopes:
            params["scopes"] = scopes
        if query_params:
            params.update({str(k): str(v) for k, v in query_params.items()})
        url = f"{self._url}/authorize?{urlencode(params)}"
        return {"data": {"provider": provider, "url": url}, "error": None}

    def sign_in_with_otp(
        self,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        create_user: Optional[bool] = None,
        captcha_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a one-time password (magic link or SMS)."""
        body: Dict[str, Any] = {}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if data:
            body["data"] = data
        if create_user is not None:
            body["create_user"] = create_user
        if captcha_token:
            body["gotcha"] = captcha_token

        resp = self._req(
            "/otp",
            method="POST",
            json=body,
        )
        return handle_response(resp)

    def verify_otp(
        self,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        token: str,
        type: str,
    ) -> AuthResponse:
        """Verify an OTP or magic link token."""
        body: Dict[str, Any] = {"token": token, "type": type}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone

        resp = self._req(
            "/verify",
            method="POST",
            json=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        d = result["data"]
        if d.get("access_token"):
            session = Session.from_dict(d)
            self._set_session(session)
            self._notify("SIGNED_IN", session)
            return AuthResponse(session=session, user=session.user)
        # No session in the reply (e.g. an email change): hand back the user if there is one.
        return AuthResponse(user=User.from_dict(d) if isinstance(d, dict) and d.get("id") else None)

    def sign_in_anonymously(
        self,
        *,
        data: Optional[Dict[str, Any]] = None,
        captcha_token: Optional[str] = None,
    ) -> AuthResponse:
        """Create an anonymous user and session."""
        body: Dict[str, Any] = {}
        if data:
            body["data"] = data
        if captcha_token:
            body["gotcha"] = captcha_token

        resp = self._req(
            "/signup",
            method="POST",
            json=body,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        d = result["data"] or {}
        if not d.get("access_token"):
            return AuthResponse(user=User.from_dict(d) if d.get("id") else None)
        session = Session.from_dict(d)
        self._set_session(session)
        self._notify("SIGNED_IN", session)
        return AuthResponse(session=session, user=session.user)

    # ─── Password / User Update ──────────────────────────────────────

    def reset_password_for_email(
        self,
        email: str,
        *,
        redirect_to: Optional[str] = None,
        captcha_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a password reset email."""
        body: Dict[str, Any] = {"email": email}
        if redirect_to:
            body["redirect_to"] = redirect_to
        if captcha_token:
            body["gotcha"] = captcha_token

        resp = self._req(
            "/recover",
            method="POST",
            json=body,
        )
        return handle_response(resp)

    def update_user(self, attributes: Dict[str, Any]) -> AuthResponse:
        """Update the current user's attributes (email, password, metadata)."""
        if not self._session:
            return AuthResponse(error={"message": "Not authenticated"})

        resp = self._req(
            "/user",
            method="PUT",
            access_token=self._session.access_token,
            json=attributes,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        user = User.from_dict(result["data"] or {})
        self._session.user = user
        self._save()
        self._notify("USER_UPDATED", self._session)
        return AuthResponse(session=self._session, user=user)

    # ─── Account deletion ────────────────────────────────────────────

    def delete_user(self, user_id: str, *, should_soft_delete: bool = False) -> Dict[str, Any]:
        """Permanently delete a user.

        GoTrue has no self-service delete — this is an administrative endpoint —
        so the client must be built with the **service key**, and this must not
        run anywhere the key could be read by the people it protects against.
        Call it from your own backend, once you have established that the person
        asking is the person being deleted.

        ``should_soft_delete`` keeps the row and clears the identity instead of
        removing it. That leaves the email address occupied, so the person
        cannot sign up again with it; the default is a real delete.

        Deleting the signed-in user also ends the session held here, which would
        otherwise go on refreshing a token for somebody who no longer exists.
        """
        resp = self._req(
            f"/admin/users/{quote(user_id, safe='')}",
            method="DELETE",
            access_token=self._api_key,
            json={"should_soft_delete": should_soft_delete},
        )
        result = handle_response(resp)
        if result["error"]:
            return {"data": None, "error": result["error"]}

        if self._session and self._session.user and self._session.user.id == user_id:
            self._remove_session()
            self._notify("SIGNED_OUT", None)

        return {"data": {}, "error": None}

    # ─── Sign Out ────────────────────────────────────────────────────

    def sign_out(self) -> Dict[str, Any]:
        """Sign out the current user and clear the session."""
        if self._session:
            try:
                self._req("/logout", method="POST", access_token=self._session.access_token)
            except Exception:
                pass  # signing out locally must work even when the server is unreachable
        self._remove_session()
        self._notify("SIGNED_OUT", None)
        return {"error": None}

    # ─── Refresh ─────────────────────────────────────────────────────

    def refresh_session(self) -> AuthResponse:
        """Manually refresh the session using the refresh token."""
        if not self._session or not self._session.refresh_token:
            return AuthResponse(error={"message": "No refresh token"})
        res = self._refresh_with(self._session.refresh_token)
        if res.session is not None:
            self._notify("TOKEN_REFRESHED", res.session)
        return res

    def _refresh_with(self, refresh_token: str) -> AuthResponse:
        resp = self._req("/token?grant_type=refresh_token", method="POST", json={"refresh_token": refresh_token})
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        session = Session.from_dict(result["data"] or {})
        self._set_session(session)
        return AuthResponse(session=session, user=session.user)

    # ─── Listeners ───────────────────────────────────────────────────

    def on_auth_state_change(self, callback: AuthChangeCallback) -> Subscription:
        """Register a listener; it is called at once with ``INITIAL_SESSION`` and the current session.

        Returns a ``Subscription`` (``.unsubscribe()``; calling it also unsubscribes).
        """
        self._listener_counter += 1
        key = str(self._listener_counter)
        self._listeners[key] = callback

        def unsubscribe() -> None:
            self._listeners.pop(key, None)

        try:
            callback(AuthChangeEvent.INITIAL_SESSION, self._session)
        except Exception:
            pass
        return Subscription(id=f"auth-listener-{key}", unsubscribe=unsubscribe)

    # ─── Private helpers ─────────────────────────────────────────────

    def _set_session(self, session: Session) -> None:
        if not self._persist:
            return  # stateless mode: never hold a session
        if session.expires_at is None:
            session.expires_at = int(time.time()) + session.expires_in
        self._session = session
        self._save()
        self._schedule_refresh()

    def _remove_session(self) -> None:
        self._session = None
        self._cancel_refresh()
        self._remove_stored()

    def _schedule_refresh(self) -> None:
        self._cancel_refresh()
        if not self._auto_refresh or not self._session or not self._session.expires_at:
            return
        delay = max(1.0, self._session.expires_at - time.time() - REFRESH_MARGIN)
        timer = threading.Timer(delay, self._auto_refresh_now)
        timer.daemon = True
        self._refresh_timer = timer
        timer.start()

    def _cancel_refresh(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def _auto_refresh_now(self) -> None:
        if not self._session or not self._session.refresh_token:
            return
        try:
            res = self._refresh_with(self._session.refresh_token)
        except Exception as e:  # network error
            res = AuthResponse(error={"message": str(e)})
        if res.session is not None:
            self._notify("TOKEN_REFRESHED", res.session)
        else:
            self._remove_session()
            self._notify("SIGNED_OUT", None)

    def _save(self) -> None:
        if self._storage is None or not self._persist or self._session is None:
            return
        try:
            self._storage.set_item(STORAGE_KEY, json.dumps(self._session.to_dict()))
        except Exception:
            pass

    def _remove_stored(self) -> None:
        if self._storage is None:
            return
        try:
            self._storage.remove_item(STORAGE_KEY)
        except Exception:
            pass

    def _load_stored(self) -> Optional[Session]:
        if self._storage is None or not self._persist:
            return None
        try:
            raw = self._storage.get_item(STORAGE_KEY)
            if not raw:
                return None
            data = json.loads(raw)
            return Session.from_dict(data) if isinstance(data, dict) and data.get("access_token") else None
        except Exception:
            return None

    def _notify(self, event: str, session: Optional[Session]) -> None:
        ev = AuthChangeEvent(event)
        for cb in list(self._listeners.values()):
            try:
                cb(ev, session)
            except Exception:
                pass
