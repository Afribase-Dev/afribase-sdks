"""AfribaseAuthClient — authentication and user management."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from afribase._http import handle_response, sync_request
from afribase._types import (
    AuthChangeCallback,
    AuthChangeEvent,
    AuthResponse,
    Session,
    User,
)


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
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._auto_refresh = auto_refresh_token
        self._persist = persist_session
        self._headers = headers or {}
        self._session: Optional[Session] = None
        self._listeners: Dict[str, AuthChangeCallback] = {}
        self._listener_counter = 0

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

    # ─── Session ──────────────────────────────────────────────────────

    def get_session(self) -> AuthResponse:
        """Return the current session."""
        return AuthResponse(session=self._session)

    def get_user(self) -> AuthResponse:
        """Fetch the user from the server using the current access token."""
        if not self._session:
            return AuthResponse(error={"message": "Not authenticated"})
        resp = sync_request(
            f"{self._url}/user",
            api_key=self._api_key,
            access_token=self._session.access_token,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        user = User.from_dict(result["data"])
        self._session.user = user
        return AuthResponse(user=user, session=self._session)

    def set_session(self, access_token: str, refresh_token: str) -> AuthResponse:
        """Manually set a session from existing tokens."""
        resp = sync_request(
            f"{self._url}/user",
            api_key=self._api_key,
            access_token=access_token,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        user = User.from_dict(result["data"])
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

        resp = sync_request(
            f"{self._url}/signup",
            method="POST",
            api_key=self._api_key,
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

        resp = sync_request(
            f"{self._url}/token?grant_type=password",
            method="POST",
            api_key=self._api_key,
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
        params: List[str] = [f"provider={provider}"]
        if redirect_to:
            params.append(f"redirect_to={redirect_to}")
        if scopes:
            params.append(f"scopes={scopes}")
        if query_params:
            for k, v in query_params.items():
                params.append(f"{k}={v}")
        url = f"{self._url}/authorize?{'&'.join(params)}"
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

        resp = sync_request(
            f"{self._url}/otp",
            method="POST",
            api_key=self._api_key,
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

        resp = sync_request(
            f"{self._url}/verify",
            method="POST",
            api_key=self._api_key,
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
        return AuthResponse()

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

        resp = sync_request(
            f"{self._url}/signup",
            method="POST",
            api_key=self._api_key,
            json=body,
            headers={"Content-Type": "application/json", "X-Afribase-Anonymous": "true"},
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        session = Session.from_dict(result["data"])
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

        resp = sync_request(
            f"{self._url}/recover",
            method="POST",
            api_key=self._api_key,
            json=body,
        )
        return handle_response(resp)

    def update_user(self, attributes: Dict[str, Any]) -> AuthResponse:
        """Update the current user's attributes (email, password, metadata)."""
        if not self._session:
            return AuthResponse(error={"message": "Not authenticated"})

        resp = sync_request(
            f"{self._url}/user",
            method="PUT",
            api_key=self._api_key,
            access_token=self._session.access_token,
            json=attributes,
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])

        user = User.from_dict(result["data"])
        self._session.user = user
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
        resp = sync_request(
            f"{self._url}/admin/users/{user_id}",
            method="DELETE",
            api_key=self._api_key,
            access_token=self._api_key,
            json={"should_soft_delete": should_soft_delete},
        )
        result = handle_response(resp)
        if result["error"]:
            return {"error": result["error"]}

        if self._session and self._session.user and self._session.user.id == user_id:
            self._session = None
            self._notify("SIGNED_OUT", None)

        return {"error": None}

    # ─── Sign Out ────────────────────────────────────────────────────

    def sign_out(self) -> Dict[str, Any]:
        """Sign out the current user and clear the session."""
        if self._session:
            sync_request(
                f"{self._url}/logout",
                method="POST",
                api_key=self._api_key,
                access_token=self._session.access_token,
            )
        self._session = None
        self._notify("SIGNED_OUT", None)
        return {"error": None}

    # ─── Refresh ─────────────────────────────────────────────────────

    def refresh_session(self) -> AuthResponse:
        """Manually refresh the session using the refresh token."""
        if not self._session:
            return AuthResponse(error={"message": "No session"})
        resp = sync_request(
            f"{self._url}/token?grant_type=refresh_token",
            method="POST",
            api_key=self._api_key,
            json={"refresh_token": self._session.refresh_token},
        )
        result = handle_response(resp)
        if result["error"]:
            return AuthResponse(error=result["error"])
        session = Session.from_dict(result["data"])
        self._set_session(session)
        self._notify("TOKEN_REFRESHED", session)
        return AuthResponse(session=session, user=session.user)

    # ─── Listeners ───────────────────────────────────────────────────

    def on_auth_state_change(self, callback: AuthChangeCallback) -> Callable[[], None]:
        """Register a listener for auth state changes. Returns an unsubscribe function."""
        self._listener_counter += 1
        key = str(self._listener_counter)
        self._listeners[key] = callback

        def unsubscribe() -> None:
            self._listeners.pop(key, None)

        return unsubscribe

    # ─── Private helpers ─────────────────────────────────────────────

    def _set_session(self, session: Session) -> None:
        if session.expires_at is None:
            session.expires_at = int(time.time()) + session.expires_in
        self._session = session

    def _notify(self, event: str, session: Optional[Session]) -> None:
        ev = AuthChangeEvent(event)
        for cb in list(self._listeners.values()):
            try:
                cb(ev, session)
            except Exception:
                pass
