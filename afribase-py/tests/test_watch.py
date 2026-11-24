import asyncio
import json
import logging
import threading

import pytest

from afribase import watch
from afribase.watch import _client


class Recorder:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, url, body, headers):
        with self.lock:
            self.calls.append((url, json.loads(body), headers))

    @property
    def events(self):
        return [e for _, b, _ in self.calls for e in b["events"]]


@pytest.fixture
def rec():
    r = Recorder()
    client = watch.init_watch("abw_test", "https://api.example.com/watch/ingest", release="1.2.0",
                              environment="prod", transport=r, background=False, http=False,
                              logging_breadcrumbs=False, retry_backoff=0)
    yield r
    watch.stop(0)


def boom():
    raise ValueError("card for bob@example.com declined")


def test_event_shape_matches_js_sdk(rec):
    try:
        boom()
    except ValueError:
        ev = watch.capture_exception(context={"order": 7}, session_id="sess-1", url="/pay?card=4111", method="post")
    url, body, headers = rec.calls[0]
    assert url == "https://api.example.com/watch/ingest?key=abw_test"
    assert headers["Content-Type"] == "application/json"
    assert list(body) == ["events"] and body["events"][0] == ev
    assert ev["kind"] == "error"
    assert ev["message"] == "ValueError: card for bob@example.com declined"
    assert "Traceback" in ev["stack"] and "boom" in ev["stack"]
    assert ev["release"] == "1.2.0" and ev["environment"] == "prod"
    assert ev["sessionId"] == "sess-1"
    assert ev["url"] == "/pay"  # query dropped
    assert ev["method"] == "POST"
    assert ev["platform"] == "python" and ev["context"]["platform"] == "python" and ev["context"]["order"] == 7
    assert ev["timestamp"].endswith("Z")
    assert isinstance(ev["breadcrumbs"], list)
    # Only fields the ingest endpoint knows (plus platform, which it ignores).
    known = {"kind", "message", "stack", "url", "method", "status", "durationMs", "release", "environment",
             "userId", "sessionId", "breadcrumbs", "context", "timestamp", "platform"}
    assert set(ev) <= known


def test_noop_before_init_and_without_exception():
    _client._client = None
    assert watch.capture_exception(ValueError("x")) is None
    r = Recorder()
    c = watch.WatchClient("k", "https://x/watch/ingest?region=eu", transport=r, background=False, http=False,
                          logging_breadcrumbs=False)
    assert c.capture_exception() is None  # nothing being handled
    c.capture_exception(KeyError("k"))
    assert r.calls[0][0] == "https://x/watch/ingest?region=eu&key=k"


def test_transport_errors_never_raise():
    def broken(url, body, headers):
        raise OSError("down")

    c = watch.WatchClient("k", "https://x/i", transport=broken, background=False, http=False,
                          logging_breadcrumbs=False, retry_backoff=0)
    assert c.capture_exception(RuntimeError("x"))["kind"] == "error"


def test_background_batches_and_flush():
    r = Recorder()
    c = watch.WatchClient("k", "https://x/i", transport=r, background=True, http=False, logging_breadcrumbs=False)
    for i in range(120):
        c.capture_exception(RuntimeError(str(i)))
    c.flush(5)
    assert len(r.events) == 120
    assert all(len(b["events"]) <= 50 for _, b, _ in r.calls)
    c.close(1)
    assert c.capture_exception(RuntimeError("late")) is None


def test_sample_rate_zero_drops():
    r = Recorder()
    c = watch.WatchClient("k", "https://x/i", transport=r, background=False, sample_rate=0, http=False,
                          logging_breadcrumbs=False)
    assert c.capture_exception(RuntimeError("x")) is None and not r.calls
    # Sampling applies to errors only, like the JS SDK.
    assert c.capture_message("hello")["kind"] == "log" and len(r.calls) == 1


def test_user_callable_and_session_cleaning():
    r = Recorder()
    c = watch.WatchClient("k", "https://x/i", transport=r, background=False, user=lambda: "u-1", http=False,
                          logging_breadcrumbs=False)
    ev = c.capture_exception(RuntimeError("x"), session_id=" a b\nc" + "x" * 100)
    assert ev["userId"] == "u-1"
    assert ev["sessionId"] == ("a b\nc" + "x" * 100)[:64].replace(" ", "").replace("\n", "")


def test_request_context_used_by_plain_capture(rec):
    token = watch.begin_request("sess-ctx", "/orders/9?x=1", "get")
    try:
        watch.capture_exception(RuntimeError("x"))
    finally:
        watch.end_request(token)
    ev = rec.events[0]
    assert ev["sessionId"] == "sess-ctx" and ev["url"] == "/orders/9" and ev["method"] == "GET"
    watch.capture_exception(RuntimeError("y"))
    assert "sessionId" not in rec.events[1]


def test_session_from_headers():
    assert watch.session_from_headers({"x-watch-session": "abc"}) == "abc"
    assert watch.session_from_headers({"X-WATCH-SESSION": "abc"}) == "abc"
    assert watch.session_from_headers({}) is None
    assert watch.session_from_headers(None) is None


def test_init_requires_key():
    with pytest.raises(ValueError):
        watch.init_watch("", "https://x")


# ── Parity with the JS SDK ────────────────────────────────────────────────


def test_capture_error_accepts_any_value_like_js(rec):
    ev = watch.capture_error("Payment provider said no", {"provider": "paystack"})
    assert ev["kind"] == "error" and ev["message"] == "Payment provider said no" and "stack" not in ev
    assert ev["context"]["provider"] == "paystack"
    ev = watch.capture_error(KeyError("sku"), {"order": 1})
    assert ev["message"] == "KeyError: 'sku'" and ev["context"]["order"] == 1


def test_capture_message_is_a_log_event(rec):
    ev = watch.capture_message("cache cold", level="warning", context={"region": "eu"})
    assert ev["kind"] == "log" and ev["message"] == "cache cold"
    assert ev["context"]["level"] == "warning" and ev["context"]["region"] == "eu"


def test_strip_query_like_js():
    assert watch.strip_query("https://bob:pw@api.x.com:8443/v1/pay?token=abc#frag") == "https://api.x.com:8443/v1/pay"
    assert watch.strip_query("/orders?email=bob@example.com") == "/orders"
    assert watch.strip_query(None) is None


def test_breadcrumbs_per_request_capped_and_structured(rec):
    token = watch.begin_request("s", "/a?secret=1", "post")
    try:
        for i in range(40):
            watch.add_breadcrumb("custom", step=i, note="x" * 400, ok=True, skip=None)
        ev = watch.capture_exception(RuntimeError("x"))
    finally:
        watch.end_request(token)
    crumbs = ev["breadcrumbs"]
    assert len(crumbs) == 30 and crumbs[-1]["step"] == 39 and crumbs[0]["step"] == 10
    assert len(crumbs[-1]["note"]) == 300 and crumbs[-1]["ok"] is True and "skip" not in crumbs[-1]
    assert all(isinstance(c["t"], int) and c["type"] == "custom" for c in crumbs)
    # Another request starts clean: crumbs never leak between users.
    token = watch.begin_request("s2", "/b", "get")
    try:
        ev2 = watch.capture_exception(RuntimeError("y"))
    finally:
        watch.end_request(token)
    assert ev2["breadcrumbs"] == [{"t": ev2["breadcrumbs"][0]["t"], "type": "request", "method": "GET", "url": "/b"}]


def test_slow_request_event(rec):
    c = watch.get_client()
    c.slow_ms = 1
    token = watch.begin_request("s9", "/report?x=1", "get")
    import time as _t

    _t.sleep(0.01)
    watch.end_request(token, 200)
    ev = rec.events[-1]
    assert ev["kind"] == "slow" and ev["url"] == "/report" and ev["method"] == "GET" and ev["status"] == 200
    assert ev["durationMs"] >= 1 and ev["message"].startswith("Slow request: GET /report ")
    assert ev["sessionId"] == "s9"


def test_logging_breadcrumbs_and_log_events():
    r = Recorder()
    c = watch.WatchClient("k", "https://x/i", transport=r, background=False, http=False,
                          log_event_level=logging.ERROR)
    log = logging.getLogger("shop.pay")
    try:
        token = watch.begin_request("s", "/pay", "post")
        try:
            log.info("not kept")
            log.warning("retrying card")
            log.error("gateway down for %s", "eu")
            try:
                raise ValueError("bad amount")
            except ValueError:
                log.exception("charge failed")
        finally:
            watch.end_request(token)
    finally:
        c.stop(0)
    kinds = [(e["kind"], e["message"]) for e in r.events]
    assert kinds == [("log", "gateway down for eu"), ("error", "ValueError: bad amount")]
    crumbs = r.events[-1]["breadcrumbs"]
    assert [x.get("message") for x in crumbs if x["type"] == "console"] == ["retrying card", "gateway down for eu"]
    # stop() removed the handler.
    assert not any(isinstance(h, _client._LogHandler) for h in logging.getLogger().handlers)


def test_batches_split_by_count_and_size():
    r = Recorder()
    c = watch.WatchClient("k", "https://x/i", transport=r, background=False, http=False, logging_breadcrumbs=False)
    evs = [{"kind": "log", "message": "m" * 1900, "context": {"pad": "p" * 9000}} for _ in range(60)]
    bodies = c._bodies(evs)
    assert all(len(b) <= _client.MAX_BODY for b in bodies)
    assert sum(len(json.loads(b)["events"]) for b in bodies) == 60
    assert all(len(json.loads(b)["events"]) <= 50 for b in bodies)
    small = c._bodies([{"kind": "log", "message": "x"}] * 120)
    assert [len(json.loads(b)["events"]) for b in small] == [50, 50, 20]
    huge = c._bodies([{"kind": "error", "message": "x", "stack": "s" * 300000, "breadcrumbs": [{"t": 1}]}])
    ev = json.loads(huge[0])["events"][0]
    assert len(ev["stack"]) == 4000 and ev["breadcrumbs"] == []


def test_retry_with_backoff_then_give_up_on_4xx():
    statuses = [None]
    calls = []

    def flaky(url, body, headers):
        calls.append(1)
        s = statuses.pop(0) if statuses else 202
        if s == "boom":
            raise OSError("network down")
        return s

    c = watch.WatchClient("k", "https://x/i", transport=flaky, background=False, http=False,
                          logging_breadcrumbs=False, retry_backoff=0.001, max_retries=3)
    statuses[:] = ["boom", 503, 429, 202]
    c.capture_message("a")
    assert len(calls) == 4
    calls.clear()
    statuses[:] = [400, 202]
    c.capture_message("b")
    assert len(calls) == 1  # 4xx is not retried
    calls.clear()
    statuses[:] = [500, 500, 500, 500, 500]
    c.capture_message("c")
    assert len(calls) == 4  # 1 + max_retries, then dropped


def test_http_instrumentation_requests_and_httpx():
    httpx = pytest.importorskip("httpx")
    r = Recorder()

    def handler(request):
        if request.url.path == "/down":
            return httpx.Response(502)
        if request.url.path == "/boom":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200)

    c = watch.WatchClient("k", "https://watch.example.com/watch/ingest", transport=r, background=False,
                          logging_breadcrumbs=False)
    try:
        token = watch.begin_request("s-http", "/checkout", "post")
        try:
            with httpx.Client(transport=httpx.MockTransport(handler)) as hc:
                hc.get("https://pay.example.com/ok?card=4111")
                hc.post("https://pay.example.com/down?token=abc")
                with pytest.raises(httpx.ConnectError):
                    hc.get("https://pay.example.com/boom")
                hc.post("https://watch.example.com/watch/ingest?key=k")  # own endpoint: ignored

            async def go():
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as ac:
                    await ac.get("https://pay.example.com/down")

            asyncio.run(go())
        finally:
            watch.end_request(token)
    finally:
        c.stop(0)
    http_events = [e for e in r.events if e["kind"] == "http"]
    assert [e["message"] for e in http_events] == [
        "POST https://pay.example.com/down -> 502",
        "GET https://pay.example.com/boom failed: refused",
        "GET https://pay.example.com/down -> 502",
    ]
    assert http_events[0]["status"] == 502 and http_events[1]["status"] == 0 and http_events[0]["sessionId"] == "s-http"
    fetches = [x for x in http_events[-1]["breadcrumbs"] if x["type"] == "fetch"]
    assert [(x["method"], x["url"], x["status"]) for x in fetches] == [
        ("GET", "https://pay.example.com/ok", 200),
        ("POST", "https://pay.example.com/down", 502),
        ("GET", "https://pay.example.com/boom", 0),
        ("GET", "https://pay.example.com/down", 502),
    ]
    assert all("card" not in json.dumps(e) and "token=abc" not in json.dumps(e) for e in r.events)
    # stop() restored httpx.
    assert httpx.Client.send.__qualname__.startswith("Client.")

    requests = pytest.importorskip("requests")
    r2 = Recorder()
    c2 = watch.WatchClient("k", "https://w/i", transport=r2, background=False, logging_breadcrumbs=False)
    try:
        from requests.adapters import BaseAdapter

        class Fake(BaseAdapter):
            def send(self, request, **kw):
                resp = requests.Response()
                resp.status_code = 500
                resp.request = request
                return resp

            def close(self):
                pass

        s = requests.Session()
        s.mount("https://", Fake())
        s.get("https://api.example.com/v1?x=1")
    finally:
        c2.stop(0)
    assert r2.events[0]["kind"] == "http" and r2.events[0]["message"] == "GET https://api.example.com/v1 -> 500"


def test_stop_stops_sending(rec):
    watch.stop(0)
    assert watch.capture_exception(RuntimeError("late")) is None


# ── ASGI (no framework needed) ─────────────────────────────────────────────


def test_asgi_middleware_reports_and_reraises(rec):
    from afribase.watch.asgi import WatchMiddleware

    async def app(scope, receive, send):
        raise ZeroDivisionError("division by zero")

    mw = WatchMiddleware(app)
    scope = {"type": "http", "path": "/checkout", "method": "POST", "headers": [(b"x-watch-session", b"mob-42")]}

    async def receive():
        return {"type": "http.request"}

    async def send(msg):
        pass

    with pytest.raises(ZeroDivisionError):
        asyncio.run(mw(scope, receive, send))
    ev = rec.events[0]
    assert ev["sessionId"] == "mob-42" and ev["url"] == "/checkout" and ev["method"] == "POST" and ev["status"] == 500
    assert ev["context"]["framework"] == "asgi"
    # lifespan passes straight through
    seen = []

    async def ok(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(WatchMiddleware(ok)({"type": "lifespan"}, receive, send))
    assert seen == ["lifespan"]


# ── Frameworks (skipped when not installed) ────────────────────────────────


def test_fastapi(rec):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from afribase.watch.starlette import WatchMiddleware

    app = FastAPI()
    app.add_middleware(WatchMiddleware, framework="fastapi")

    @app.get("/fail")
    def fail():
        raise RuntimeError("fastapi broke")

    @app.get("/missing")
    def missing():
        raise HTTPException(404)

    @app.get("/inner")
    def inner():
        watch.capture_exception(RuntimeError("handled"))
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/fail", headers={"X-Watch-Session": "mob-1"}).status_code == 500
    assert client.get("/missing", headers={"X-Watch-Session": "mob-1"}).status_code == 404
    assert client.get("/inner", headers={"X-Watch-Session": "mob-2"}).status_code == 200
    assert [e["message"] for e in rec.events] == ["RuntimeError: fastapi broke", "RuntimeError: handled"]
    assert rec.events[0]["sessionId"] == "mob-1" and rec.events[0]["context"]["framework"] == "fastapi"
    assert rec.events[0]["breadcrumbs"][0] == {"t": rec.events[0]["breadcrumbs"][0]["t"], "type": "request", "method": "GET", "url": "/fail"}
    assert rec.events[1]["sessionId"] == "mob-2" and rec.events[1]["url"] == "/inner"


def test_flask(rec):
    flask = pytest.importorskip("flask")
    from afribase.watch.flask import init_flask

    app = flask.Flask(__name__)
    init_flask(app)

    @app.get("/fail")
    def fail():
        raise RuntimeError("flask broke")

    @app.get("/inner")
    def inner():
        watch.capture_exception(RuntimeError("handled"))
        return "ok"

    @app.get("/notfound")
    def notfound():
        flask.abort(404)

    c = app.test_client()
    assert c.get("/fail?token=x", headers={"X-Watch-Session": "mob-3"}).status_code == 500
    assert c.get("/notfound").status_code == 404
    assert c.get("/inner", headers={"X-Watch-Session": "mob-4"}).status_code == 200
    assert [e["message"] for e in rec.events] == ["RuntimeError: flask broke", "RuntimeError: handled"]
    e0, e1 = rec.events
    assert e0["sessionId"] == "mob-3" and e0["url"] == "/fail" and e0["method"] == "GET" and e0["context"]["framework"] == "flask"
    assert e1["sessionId"] == "mob-4"
    assert e0["breadcrumbs"][0]["type"] == "request" and e0["breadcrumbs"][0]["url"] == "/fail"


def test_django(rec):
    pytest.importorskip("django")
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            ALLOWED_HOSTS=["*"],
            ROOT_URLCONF=__name__,
            MIDDLEWARE=["afribase.watch.django.WatchMiddleware"],
            SECRET_KEY="test",
            LOGGING_CONFIG=None,
        )
        django.setup()
    from django.test import Client

    c = Client(raise_request_exception=False)
    assert c.get("/fail", HTTP_X_WATCH_SESSION="mob-5").status_code == 500
    assert c.get("/missing").status_code == 404
    assert c.get("/inner", HTTP_X_WATCH_SESSION="mob-6").status_code == 200
    assert [e["message"] for e in rec.events] == ["RuntimeError: django broke", "RuntimeError: handled"]
    e0, e1 = rec.events
    assert e0["sessionId"] == "mob-5" and e0["url"] == "/fail" and e0["method"] == "GET" and e0["context"]["framework"] == "django"
    assert e1["sessionId"] == "mob-6" and e1["url"] == "/inner"
    assert e1["breadcrumbs"][0]["type"] == "request" and e1["breadcrumbs"][0]["url"] == "/inner"


def _django_fail(request):
    raise RuntimeError("django broke")


def _django_missing(request):
    from django.http import Http404

    raise Http404()


def _django_inner(request):
    from django.http import HttpResponse

    watch.capture_exception(RuntimeError("handled"))
    return HttpResponse("ok")


def __getattr__(name):
    # Django reads urlpatterns from ROOT_URLCONF (this module) lazily.
    if name == "urlpatterns":
        from django.urls import path

        return [path("fail", _django_fail), path("missing", _django_missing), path("inner", _django_inner)]
    raise AttributeError(name)
