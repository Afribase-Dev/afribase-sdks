"""Base1 Watch client: error capture for Python backends.

The backend counterpart of the JavaScript SDK (sdks/afribase-js/src/lib/watch.ts,
afribase-js 0.6.0), per docs/watch-wireframe-contract.md "Parity with the JS SDK":

- the same config (key, endpoint, release, environment, sample_rate, user) and
  client API (capture_error / capture_exception, flush, stop);
- the same event shape and kinds: ``error``, ``log``, ``http`` (outgoing request
  failed or answered >= 500), ``slow`` (a request slower than ``slow_ms``);
- breadcrumbs (last 30, per request): ``request``, ``fetch`` (outgoing
  requests/httpx calls), ``console`` (log records), ``custom``. Structure only;
  the server masks every breadcrumb value by value before storing it;
- URLs stripped of query, fragment and credentials, like the JS ``stripQuery``;
- batches of <= 50 events and <= 256 KB, retried with backoff on network
  errors, 429 and 5xx, flushed at exit;
- ``X-Watch-Session`` request header -> ``sessionId`` (framework integrations).

Standard library only; frameworks and HTTP clients are patched only when they are
installed. Sends from one daemon thread and never raises into the application.
"""

from __future__ import annotations

import atexit
import contextvars
import datetime as _dt
import importlib
import importlib.util
import json
import logging
import platform as _platform
import queue
import random
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Mapping, Optional

SESSION_HEADER = "X-Watch-Session"

MAX_MESSAGE = 2000
MAX_STACK = 16000
MAX_CRUMBS = 30
MAX_CRUMB_TEXT = 300
MAX_BATCH = 50  # the server accepts at most 50 events per request
MAX_BODY = 250 * 1024  # under the server's 256 KB body limit
MAX_QUEUE = 500
MAX_SESSION_ID = 64
SLOW_MS = 4000  # same threshold as the JS SDK's slow page

# A transport posts one body and returns the HTTP status (None = 2xx / unknown).
Transport = Callable[[str, bytes, Dict[str, str]], Optional[int]]


class _RequestState:
    __slots__ = ("session_id", "url", "method", "crumbs", "started")

    def __init__(self, session_id: Optional[str], url: str, method: str) -> None:
        self.session_id = session_id
        self.url = url
        self.method = method
        self.crumbs: List[Dict[str, Any]] = []
        self.started = time.monotonic()


# The request being handled (set by the framework integrations).
_request: contextvars.ContextVar[Optional[_RequestState]] = contextvars.ContextVar("afribase_watch_request", default=None)
# Breadcrumbs outside any request (scripts, workers).
_global_crumbs: List[Dict[str, Any]] = []
_global_lock = threading.Lock()

_client: Optional["WatchClient"] = None
_client_lock = threading.Lock()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clean_session(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip()[:MAX_SESSION_ID]
    # Session ids are opaque tokens: keep printable ASCII only.
    value = "".join(ch for ch in value if 33 <= ord(ch) < 127)
    return value or None


def strip_query(url: Optional[str]) -> Optional[str]:
    """Origin + path only: drops query, fragment and user:password@ (they carry secrets)."""
    if not url:
        return None
    s = str(url)
    try:
        p = urllib.parse.urlsplit(s)
        if p.scheme and p.netloc:
            host = p.hostname or ""
            if ":" in host:
                host = "[" + host + "]"
            netloc = host + (":" + str(p.port) if p.port else "")
            return urllib.parse.urlunsplit((p.scheme, netloc, p.path, "", ""))
    except ValueError:
        pass
    return s.split("?", 1)[0].split("#", 1)[0]


# ── Request context ─────────────────────────────────────────────────────────


def begin_request(session_id: Optional[str] = None, url: Optional[str] = None,
                  method: Optional[str] = None) -> contextvars.Token[Optional[_RequestState]]:
    """Marks the start of a request: fresh breadcrumbs, its session, path and method.

    Returns a token for :func:`end_request`. Used by the framework integrations;
    call it yourself for other servers or job runners.
    """
    state = _RequestState(_clean_session(session_id), strip_query(url) or "", (method or "").upper()[:10])
    token = _request.set(state)
    add_breadcrumb("request", method=state.method or None, url=state.url or None)
    return token


def end_request(token: contextvars.Token[Optional[_RequestState]], status: Optional[int] = None) -> None:
    """Ends a request; reports a ``slow`` event when it took longer than the client's ``slow_ms``."""
    state = _request.get()
    try:
        if state is not None:
            ms = int((time.monotonic() - state.started) * 1000)
            client = _client
            if client is not None and client.slow_ms and ms > client.slow_ms:
                client._push({
                    "kind": "slow",
                    "message": ("Slow request: %s %s %d ms" % (state.method, state.url, ms)).strip()[:MAX_MESSAGE],
                    "url": state.url or None, "method": state.method or None,
                    "status": status, "durationMs": ms,
                })
    finally:
        try:
            _request.reset(token)
        except ValueError:  # different context (e.g. another thread)
            _request.set(None)


def session_from_headers(headers: Any) -> Optional[str]:
    """Reads X-Watch-Session from a mapping of headers (case-insensitive)."""
    if headers is None:
        return None
    try:
        v = headers.get(SESSION_HEADER)
        if v is None:
            v = headers.get(SESSION_HEADER.lower())
        if v is None and isinstance(headers, Mapping):
            for k, val in headers.items():
                if isinstance(k, str) and k.lower() == SESSION_HEADER.lower():
                    v = val
                    break
        return _clean_session(v)
    except Exception:
        return None


def _crumb_value(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return str(v)[:MAX_CRUMB_TEXT]


def add_breadcrumb(type: str, **data: Any) -> None:
    """Adds a breadcrumb (``{"t", "type", ...data}``) to the current request, or the global trail."""
    crumb: Dict[str, Any] = {"t": _now_ms(), "type": str(type)[:30]}
    for k, v in data.items():
        if v is not None:
            crumb[str(k)[:40]] = _crumb_value(v)
    state = _request.get()
    if state is not None:
        state.crumbs.append(crumb)
        if len(state.crumbs) > MAX_CRUMBS:
            del state.crumbs[: len(state.crumbs) - MAX_CRUMBS]
        return
    with _global_lock:
        _global_crumbs.append(crumb)
        if len(_global_crumbs) > MAX_CRUMBS:
            del _global_crumbs[: len(_global_crumbs) - MAX_CRUMBS]


def _current_crumbs() -> List[Dict[str, Any]]:
    state = _request.get()
    if state is not None:
        return list(state.crumbs)
    with _global_lock:
        return list(_global_crumbs)


# ── Transport ───────────────────────────────────────────────────────────────


def _urllib_transport(url: str, body: bytes, headers: Dict[str, str]) -> Optional[int]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 (endpoint is set by the developer)
            resp.read()
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def _ingest_url(endpoint: str, key: str) -> str:
    sep = "&" if "?" in endpoint else "?"
    return endpoint + sep + "key=" + urllib.parse.quote(key, safe="")


def _retryable(status: Optional[int]) -> bool:
    return status is not None and (status == 429 or status >= 500)


# ── Client ──────────────────────────────────────────────────────────────────


class _LogHandler(logging.Handler):
    """Log records -> ``console`` breadcrumbs, and ``log`` events at ``event_level`` and up."""

    def __init__(self, client: "WatchClient", crumb_level: int, event_level: Optional[int]) -> None:
        super().__init__(level=crumb_level)
        self.client = client
        self.event_level = event_level

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("afribase.watch") or getattr(record, "_afribase_watch", False):
            return
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        level = record.levelname.lower()
        try:
            if self.event_level is not None and record.levelno >= self.event_level:
                if record.exc_info and record.exc_info[1] is not None:
                    self.client.capture_exception(record.exc_info[1], context={"logger": record.name, "log": msg[:MAX_CRUMB_TEXT]})
                else:
                    self.client.capture_message(msg, level=level, context={"logger": record.name})
            add_breadcrumb("console", level=level, logger=record.name, message=msg)
        except Exception:
            pass


class WatchClient:
    """Captures errors and sends them to Base1 Watch."""

    def __init__(self, key: str, endpoint: str, release: Optional[str] = None,
                 environment: Optional[str] = None, *, sample_rate: float = 1.0,
                 user: Optional[Callable[[], Optional[str]]] = None,
                 slow_ms: Optional[int] = SLOW_MS, http: bool = True,
                 logging_breadcrumbs: bool = True, log_breadcrumb_level: int = logging.WARNING,
                 log_event_level: Optional[int] = None,
                 transport: Optional[Transport] = None, background: bool = True,
                 max_retries: int = 3, retry_backoff: float = 1.0) -> None:
        self.key = key
        self.endpoint = endpoint
        self.release = release
        self.environment = environment
        self.sample_rate = max(0.0, min(1.0, float(sample_rate)))
        self.user = user
        self.slow_ms = slow_ms
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))
        self._transport = transport or _urllib_transport
        self._url = _ingest_url(endpoint, key)
        self._background = background
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=MAX_QUEUE)
        self._closed = False
        self._stopping = threading.Event()
        self._undo: List[Callable[[], None]] = []
        self._thread: Optional[threading.Thread] = None
        if background:
            self._thread = threading.Thread(target=self._worker, name="afribase-watch", daemon=True)
            self._thread.start()
            atexit.register(self.close)
        if http:
            self._instrument_http()
        if logging_breadcrumbs:
            handler = _LogHandler(self, log_breadcrumb_level, log_event_level)
            root = logging.getLogger()
            root.addHandler(handler)
            self._undo.append(lambda: root.removeHandler(handler))

    # ── capture ──────────────────────────────────────────────────────────

    def capture_error(self, err: Any = None, context: Optional[Dict[str, Any]] = None,
                      **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Reports an exception, or any value (a string becomes the message), like JS ``captureError``."""
        if err is None or isinstance(err, BaseException):
            return self.capture_exception(err, context=context, **kwargs)
        try:
            return self._push({"kind": "error", "message": str(err)[:MAX_MESSAGE], "context": context}, **kwargs)
        except Exception:
            return None

    def capture_exception(self, exc: Optional[BaseException] = None, *,
                          context: Optional[Dict[str, Any]] = None,
                          session_id: Optional[str] = None, url: Optional[str] = None,
                          method: Optional[str] = None, status: Optional[int] = None,
                          user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Queues one error event for ``exc`` (or the exception being handled); returns it, or None when dropped."""
        try:
            if exc is None:
                import sys

                exc = sys.exc_info()[1]
                if exc is None:
                    return None
            name = type(exc).__name__
            text = str(exc)
            stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            if len(stack) > MAX_STACK:
                stack = stack[-MAX_STACK:]  # keep the frames nearest the raise
            return self._push(
                {"kind": "error", "message": (name + ": " + text if text else name)[:MAX_MESSAGE], "stack": stack,
                 "url": url, "method": method, "status": status, "context": context},
                session_id=session_id, user_id=user_id,
            )
        except Exception:
            return None  # never throw from the reporter

    def capture_message(self, message: str, level: str = "info", context: Optional[Dict[str, Any]] = None,
                        **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Sends a ``log`` event."""
        ctx = dict(context or {})
        ctx.setdefault("level", level)
        try:
            return self._push({"kind": "log", "message": str(message)[:MAX_MESSAGE], "context": ctx}, **kwargs)
        except Exception:
            return None

    def _push(self, ev: Dict[str, Any], session_id: Optional[str] = None,
              user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self._closed:
            return None
        if ev.get("kind") == "error" and self.sample_rate < 1.0 and random.random() >= self.sample_rate:
            return None
        state = _request.get()
        uid = user_id
        if uid is None and self.user is not None:
            try:
                uid = self.user()
            except Exception:
                uid = None
        ctx: Dict[str, Any] = {
            "platform": "python",
            "runtime": _platform.python_implementation() + " " + _platform.python_version(),
        }
        if ev.get("context"):
            ctx.update(ev["context"])
        method = ev.get("method") or (state.method if state else "") or ""
        out: Dict[str, Any] = {
            "kind": ev["kind"],
            "platform": "python",
            "message": ev.get("message"),
            "stack": ev.get("stack"),
            "release": self.release,
            "environment": self.environment,
            "userId": uid,
            "sessionId": _clean_session(session_id) or (state.session_id if state else None),
            "url": strip_query(ev.get("url")) or (state.url if state else None) or None,
            "method": str(method).upper() or None,
            "status": ev.get("status"),
            "durationMs": ev.get("durationMs"),
            "breadcrumbs": _current_crumbs(),
            "context": ctx,
            "timestamp": _iso_now(),
        }
        out = {k: v for k, v in out.items() if v is not None}
        self._enqueue(out)
        return out

    # ── HTTP instrumentation (requests, httpx) ───────────────────────────

    def _note_http(self, method: str, url: str, status: int, ms: int, error: Optional[BaseException]) -> None:
        clean = strip_query(url) or ""
        m = (method or "GET").upper()
        add_breadcrumb("fetch", method=m, url=clean, status=status, ms=ms)
        if error is not None:
            msg = str(error) or type(error).__name__
            self._push({"kind": "http", "message": ("%s %s failed: %s" % (m, clean, msg))[:MAX_MESSAGE],
                        "url": clean, "method": m, "status": 0, "durationMs": ms})
        elif status >= 500:
            self._push({"kind": "http", "message": "%s %s -> %d" % (m, clean, status),
                        "url": clean, "method": m, "status": status, "durationMs": ms})

    def _is_own(self, url: str) -> bool:
        return url.startswith(self.endpoint)

    def _patch(self, owner: Any, name: str, make: Callable[[Any], Any]) -> None:
        orig = getattr(owner, name, None)
        if orig is None:
            return
        wrapped = make(orig)
        setattr(owner, name, wrapped)

        def undo() -> None:
            if getattr(owner, name, None) is wrapped:
                setattr(owner, name, orig)

        self._undo.append(undo)

    def _instrument_http(self) -> None:
        client = self
        if importlib.util.find_spec("requests") is not None:
            try:
                sessions = importlib.import_module("requests.sessions")

                def make_requests(orig: Any) -> Any:
                    def send(self: Any, request: Any, **kw: Any) -> Any:
                        url, method = str(getattr(request, "url", "")), str(getattr(request, "method", "GET"))
                        if client._is_own(url) or client._closed:
                            return orig(self, request, **kw)
                        started = time.monotonic()
                        try:
                            resp = orig(self, request, **kw)
                        except Exception as e:
                            client._note_http(method, url, 0, int((time.monotonic() - started) * 1000), e)
                            raise
                        client._note_http(method, url, int(getattr(resp, "status_code", 0) or 0),
                                          int((time.monotonic() - started) * 1000), None)
                        return resp

                    return send

                self._patch(sessions.Session, "send", make_requests)
            except Exception:
                pass
        if importlib.util.find_spec("httpx") is not None:
            try:
                httpx = importlib.import_module("httpx")

                def make_sync(orig: Any) -> Any:
                    def send(self: Any, request: Any, **kw: Any) -> Any:
                        url, method = str(request.url), str(request.method)
                        if client._is_own(url) or client._closed:
                            return orig(self, request, **kw)
                        started = time.monotonic()
                        try:
                            resp = orig(self, request, **kw)
                        except Exception as e:
                            client._note_http(method, url, 0, int((time.monotonic() - started) * 1000), e)
                            raise
                        client._note_http(method, url, int(resp.status_code), int((time.monotonic() - started) * 1000), None)
                        return resp

                    return send

                def make_async(orig: Any) -> Any:
                    async def send(self: Any, request: Any, **kw: Any) -> Any:
                        url, method = str(request.url), str(request.method)
                        if client._is_own(url) or client._closed:
                            return await orig(self, request, **kw)
                        started = time.monotonic()
                        try:
                            resp = await orig(self, request, **kw)
                        except Exception as e:
                            client._note_http(method, url, 0, int((time.monotonic() - started) * 1000), e)
                            raise
                        client._note_http(method, url, int(resp.status_code), int((time.monotonic() - started) * 1000), None)
                        return resp

                    return send

                self._patch(httpx.Client, "send", make_sync)
                self._patch(httpx.AsyncClient, "send", make_async)
            except Exception:
                pass

    # ── sending ──────────────────────────────────────────────────────────

    def _enqueue(self, ev: Dict[str, Any]) -> None:
        if not self._background:
            for body in self._bodies([ev]):
                self._post(body)
            return
        try:
            self._queue.put_nowait(ev)
        except queue.Full:
            pass  # drop rather than grow without bound

    @staticmethod
    def _encode(ev: Dict[str, Any]) -> bytes:
        return json.dumps(ev, default=str, separators=(",", ":")).encode("utf-8")

    def _bodies(self, events: List[Dict[str, Any]]) -> List[bytes]:
        """Splits events into request bodies of <= 50 events and <= MAX_BODY bytes."""
        out: List[bytes] = []
        cur: List[bytes] = []
        size = 0
        for ev in events:
            enc = self._encode(ev)
            if len(enc) + 20 > MAX_BODY:
                # Too big alone: drop breadcrumbs, then shorten the stack.
                ev = dict(ev, breadcrumbs=[])
                if "stack" in ev:
                    ev["stack"] = ev["stack"][-4000:]
                enc = self._encode(ev)
                if len(enc) + 20 > MAX_BODY:
                    continue
            if cur and (len(cur) >= MAX_BATCH or size + len(enc) + 1 + 20 > MAX_BODY):
                out.append(b'{"events":[' + b",".join(cur) + b"]}")
                cur, size = [], 0
            cur.append(enc)
            size += len(enc) + 1
        if cur:
            out.append(b'{"events":[' + b",".join(cur) + b"]}")
        return out

    def _post(self, body: bytes) -> bool:
        """Posts one body, retrying network errors, 429 and 5xx with backoff. True when delivered or refused for good."""
        for attempt in range(self.max_retries + 1):
            try:
                status = self._transport(self._url, body, {"Content-Type": "application/json"})
            except Exception:
                status = -1  # network error
            if status is None or 200 <= status < 300:
                return True
            if status != -1 and not _retryable(status):
                return True  # 4xx: retrying will not help
            if attempt < self.max_retries and self.retry_backoff > 0:
                delay = self.retry_backoff * (2 ** attempt) * (0.5 + random.random() / 2)
                if self._stopping.wait(min(delay, 30.0)):
                    break  # shutting down: one last try was made
        return False

    def _worker(self) -> None:
        while True:
            ev = self._queue.get()
            if ev is None:
                self._queue.task_done()
                return
            batch = [ev]
            stop = False
            while len(batch) < MAX_QUEUE:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    stop = True
                    self._queue.task_done()
                    break
                batch.append(nxt)
            for body in self._bodies(batch):
                self._post(body)
            for _ in batch:
                self._queue.task_done()
            if stop:
                return

    def flush(self, timeout: float = 2.0) -> None:
        """Waits up to ``timeout`` seconds for queued events to be sent."""
        if not self._background or self._thread is None:
            return
        done = threading.Event()

        def wait() -> None:
            self._queue.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        done.wait(timeout)

    def stop(self, timeout: float = 2.0) -> None:
        """Flushes, removes the HTTP and logging hooks and stops sending, like JS ``stop()``."""
        if self._closed:
            return
        self.flush(timeout)
        self._closed = True
        self._stopping.set()
        while self._undo:
            try:
                self._undo.pop()()
            except Exception:
                pass
        if self._thread is not None:
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

    close = stop


def init_watch(key: str, endpoint: str, release: Optional[str] = None, environment: Optional[str] = None,
               **options: Any) -> WatchClient:
    """Starts Watch error reporting and makes it the default client.

    ``endpoint`` is the ingest URL, e.g. ``https://<api>/watch/ingest``. Options:

    - ``sample_rate`` (0..1, error events; default 1)
    - ``user``: callable returning your user id (hashed on the server, never stored raw)
    - ``slow_ms``: report requests slower than this as ``slow`` events (default 4000; None = off)
    - ``http``: breadcrumbs and ``http`` events for outgoing requests/httpx calls (default True)
    - ``logging_breadcrumbs`` / ``log_breadcrumb_level`` (default WARNING): log records as breadcrumbs
    - ``log_event_level``: also send log records at this level and up as events (default off)
    - ``max_retries`` (3), ``retry_backoff`` (1 s), ``transport``, ``background`` (for tests)
    """
    global _client
    if not key or not endpoint:
        raise ValueError("init_watch needs a key and an endpoint")
    client = WatchClient(key, endpoint, release, environment, **options)
    with _client_lock:
        old, _client = _client, client
    if old is not None:
        old.stop(0.5)
    return client


def get_client() -> Optional[WatchClient]:
    return _client


def capture_exception(exc: Optional[BaseException] = None, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Reports ``exc`` (or the exception being handled) with the default client; a no-op before init_watch."""
    client = _client
    return client.capture_exception(exc, **kwargs) if client is not None else None


def capture_error(err: Any = None, context: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """JS-style ``captureError(err, context)`` with the default client."""
    client = _client
    return client.capture_error(err, context, **kwargs) if client is not None else None


def capture_message(message: str, level: str = "info", **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Sends a ``log`` event with the default client."""
    client = _client
    return client.capture_message(message, level, **kwargs) if client is not None else None


def flush(timeout: float = 2.0) -> None:
    client = _client
    if client is not None:
        client.flush(timeout)


def stop(timeout: float = 2.0) -> None:
    """Stops the default client."""
    global _client
    with _client_lock:
        client, _client = _client, None
    if client is not None:
        client.stop(timeout)
