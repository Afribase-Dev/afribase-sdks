import json
import time

import pytest

from afribase import AuthChangeEvent, MemoryStorage, Session, User, create_client
from afribase._auth import STORAGE_KEY

URL = "https://proj.example.com"

# A user as services/auth returns it: identities and factors carry fields the
# old dataclasses did not know about.
USER = {
    "id": "u-1", "aud": "authenticated", "role": "authenticated", "email": "a@b.co",
    "created_at": "2026-01-01T00:00:00Z", "app_metadata": None, "user_metadata": {"name": "A"},
    "identities": [{"identity_id": "i-1", "id": "u-1", "user_id": "u-1", "provider": "email",
                    "last_sign_in_at": "2026-01-01T00:00:00Z", "created_at": "x", "updated_at": "y",
                    "email": "a@b.co", "brand_new_field": 1}],
    "factors": [{"id": "f-1", "factor_type": "phone", "status": "verified", "created_at": "x", "updated_at": "y",
                 "phone": "+234", "last_challenged_at": None, "web_authn_aaguid": None}],
}
TOKEN = {"access_token": "at-1", "refresh_token": "rt-1", "token_type": "bearer", "expires_in": 3600, "user": USER}


def test_user_from_dict_accepts_real_payload():
    u = User.from_dict(USER)
    assert u.identities[0].identity_id == "i-1" and u.identities[0].identity_data == {}
    assert u.factors[0].phone == "+234" and u.app_metadata == {}


def test_session_defaults_like_js():
    s = Session.from_dict({"access_token": "a", "user": None, "id": "u"})
    assert s.expires_in == 3600 and s.expires_at >= int(time.time()) + 3590 and s.user.id == "u"


def test_sign_in_listener_initial_session_and_sign_out_offline(server):
    server.on("POST", "/token?grant_type=password", json_body=TOKEN)
    c = create_client(URL, "anon", auto_refresh_token=False)
    events = []
    sub = c.auth.on_auth_state_change(lambda e, s: events.append((e, s.access_token if s else None)))
    assert events == [(AuthChangeEvent.INITIAL_SESSION, None)] and sub.id.startswith("auth-listener-")
    res = c.auth.sign_in_with_password(email="a@b.co", password="pw")
    assert res.error is None and res.session.access_token == "at-1"
    assert server.last.headers["authorization"] == "Bearer anon"

    # /logout unreachable: still signed out locally.
    def boom(request):
        raise __import__("httpx").ConnectError("down", request=request)

    server.handler, orig = boom, server.handler
    try:
        assert c.auth.sign_out() == {"error": None}
    finally:
        server.handler = orig
    assert c.auth.current_session is None and events[-1] == (AuthChangeEvent.SIGNED_OUT, None)
    n = len(c.auth._listeners)
    sub.unsubscribe()
    assert len(c.auth._listeners) == n - 1


def test_get_user_with_jwt_leaves_session_alone(server):
    server.on("GET", "/auth/v1/user", json_body=USER)
    c = create_client(URL, "anon")
    res = c.auth.get_user("caller-jwt")
    assert res.user.id == "u-1" and res.session is None and c.auth.current_session is None
    assert server.last.headers["authorization"] == "Bearer caller-jwt"
    assert c.auth.get_user().error == {"message": "Not authenticated"}


def test_stateless_mode_holds_no_session(server):
    server.on("POST", "/token?grant_type=password", json_body=TOKEN)
    c = create_client(URL, "anon", persist_session=False)
    res = c.auth.sign_in_with_password(email="a@b.co", password="pw")
    assert res.session.access_token == "at-1" and c.auth.current_session is None


def test_storage_initialize_and_refresh_expired(server):
    store = MemoryStorage()
    stored = dict(TOKEN, expires_at=int(time.time()) - 10)
    store.set_item(STORAGE_KEY, json.dumps(stored))
    server.on("POST", "/token?grant_type=refresh_token", json_body=dict(TOKEN, access_token="at-2"))
    c = create_client(URL, "anon", storage=store, auto_refresh_token=False)
    events = []
    c.auth.on_auth_state_change(lambda e, s: events.append(e))
    assert c.auth.get_session().session.access_token == "at-2"
    assert server.last_json() == {"refresh_token": "rt-1"}
    assert json.loads(store.get_item(STORAGE_KEY))["access_token"] == "at-2"
    # A valid stored session is used as-is; a failed refresh clears storage.
    store2 = MemoryStorage()
    store2.set_item(STORAGE_KEY, json.dumps(dict(TOKEN, expires_at=int(time.time()) - 10)))
    server.on("POST", "/token?grant_type=refresh_token", status=400, json_body={"msg": "Invalid Refresh Token"})
    c2 = create_client(URL, "anon", storage=store2, auto_refresh_token=False)
    res = c2.auth.get_session()
    assert res.session is None and store2.get_item(STORAGE_KEY) is None


def test_refresh_guard_and_error_shape(server):
    c = create_client(URL, "anon")
    assert c.auth.refresh_session().error == {"message": "No refresh token"}
    server.on("POST", "/token?grant_type=password", status=400, json_body={"msg": "Invalid login credentials", "code": 400})
    err = c.auth.sign_in_with_password(email="a@b.co", password="x").error
    assert err["message"] == "Invalid login credentials" and err["status"] == 400
    server.on("POST", "/signup", status=502, text="")
    assert c.auth.sign_up(email="a@b.co", password="x").error["message"] == "Request failed with status 502"


def test_anonymous_without_token_does_not_create_session(server):
    server.on("POST", "/signup", json_body={"id": "anon-1", "aud": "authenticated", "created_at": "x"})
    c = create_client(URL, "anon")
    res = c.auth.sign_in_anonymously()
    assert res.session is None and res.user.id == "anon-1" and c.auth.current_session is None
    assert "x-afribase-anonymous" not in server.last.headers


def test_oauth_url_encoded():
    c = create_client(URL, "anon")
    url = c.auth.sign_in_with_oauth(provider="google", redirect_to="https://app/cb?next=/a&b=1",
                                    query_params={"prompt": "consent"})["data"]["url"]
    assert url == ("https://proj.example.com/auth/v1/authorize?provider=google&redirect_to="
                   "https%3A%2F%2Fapp%2Fcb%3Fnext%3D%2Fa%26b%3D1&prompt=consent")


def test_admin_delete_user_encodes_and_returns_data(server):
    server.on("DELETE", "/admin/users/", status=200, json_body={})
    c = create_client(URL, "service")
    assert c.auth.admin.delete_user("a/b c") == {"data": {}, "error": None}
    assert server.last.url.raw_path == b"/auth/v1/admin/users/a%2Fb%20c"
    assert server.last_json() == {"should_soft_delete": False}


def test_verify_otp_without_session_returns_user(server):
    server.on("POST", "/verify", json_body=USER)
    c = create_client(URL, "anon")
    assert c.auth.verify_otp(email="a@b.co", token="1", type="email").user.id == "u-1"


def test_client_options(server):
    c = create_client("myref", "anon", headers={"X-App": "shop", "Authorization": "Bearer nope"})
    assert c._url == "https://myref.afribase.dev"
    server.on("GET", "/rest/v1/todos", json_body=[])
    c.from_("todos").select("*").execute()
    assert server.last.headers["x-app"] == "shop" and server.last.headers["authorization"] == "Bearer anon"
    server.on("POST", "/rpc/f", json_body=1, headers={"content-range": "0-0/7"})
    c.rpc("f", {"a": 1}, count="exact").execute()
    assert "count=exact" in server.last.headers["prefer"] and server.last.headers["x-app"] == "shop"


def test_realtime_follows_auth(server):
    server.on("POST", "/token?grant_type=password", json_body=TOKEN)
    c = create_client(URL, "anon", auto_refresh_token=False)
    rt = c.realtime
    c.auth.sign_in_with_password(email="a@b.co", password="pw")
    assert rt._access_token == "at-1"
    c.auth.sign_out()
    assert rt._access_token is None
