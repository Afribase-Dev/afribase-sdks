"""AfribaseRealtimeClient — WebSocket realtime: postgres_changes, broadcast and presence.

The public API follows the JS SDK (``channel(name, config)``, ``on(type, filter, cb)``,
``send``, ``track``, ``untrack``, ``presence_state``, ``status``, ``set_auth``,
``disconnect``). The wire format is the Phoenix protocol the Afribase realtime server
(supabase/realtime v2) speaks: every frame is ``{topic, event, payload, ref}``, channels
join with ``payload.config``, a heartbeat goes out every 30 s, and a dropped socket
reconnects with backoff and rejoins its channels.

Needs the ``websockets`` package (a dependency of afribase).
"""

from __future__ import annotations

import json as _json
import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

HEARTBEAT_S = 30.0
MAX_RECONNECTS = 10

Callback = Callable[[Any], None]
StatusCallback = Callable[[str, Optional[Exception]], None]


def _topic(name: str) -> str:
    return name if name.startswith("realtime:") else f"realtime:{name}"


class RealtimeChannel:
    """A realtime channel.

    Usage::

        channel = client.channel("room1", config={"broadcast": {"self": True}, "presence": {"key": "u1"}})
        channel.on("postgres_changes", {"event": "INSERT", "schema": "public", "table": "messages"},
                   lambda p: print(p["new"]))
        channel.on("broadcast", {"event": "typing"}, lambda m: print(m["payload"]))
        channel.on("presence", {"event": "sync"}, lambda state: print(state))
        channel.subscribe(lambda status, err: print(status))
        channel.send({"type": "broadcast", "event": "typing", "payload": {"who": "u1"}})
        channel.track({"online_at": "..."})
    """

    def __init__(self, name: str, client: "AfribaseRealtimeClient", config: Optional[Dict[str, Any]] = None) -> None:
        self.name = name[len("realtime:"):] if name.startswith("realtime:") else name
        self.topic = _topic(name)
        self._client = client
        self._config: Dict[str, Any] = dict(config or {})
        self._bindings: List[Dict[str, Any]] = []
        self._presence: Dict[str, List[Dict[str, Any]]] = {}
        self._status = "CLOSED"
        self._join_ref: Optional[str] = None
        self._status_cb: Optional[StatusCallback] = None
        self._wanted = False  # subscribe() was called and unsubscribe() was not

    @property
    def status(self) -> str:
        """SUBSCRIBED, JOINING, CHANNEL_ERROR or CLOSED."""
        return self._status

    @property
    def _subscribed(self) -> bool:  # kept for older callers
        return self._wanted

    # ─── listeners ────────────────────────────────────────────────────

    def on(self, type: str, filter: Optional[Dict[str, Any]], callback: Callback) -> "RealtimeChannel":
        """Listen for ``postgres_changes``, ``broadcast`` or ``presence`` events (JS ``on``)."""
        self._bindings.append({"type": type, "filter": dict(filter or {}), "callback": callback})
        return self

    def on_postgres_changes(self, event: str, *, schema: str = "public", table: Optional[str] = None,
                            filter: Optional[str] = None, callback: Optional[Callback] = None) -> "RealtimeChannel":
        f: Dict[str, Any] = {"event": event, "schema": schema}
        if table:
            f["table"] = table
        if filter:
            f["filter"] = filter
        return self.on("postgres_changes", f, callback or (lambda _p: None))

    def on_broadcast(self, event: str, *, callback: Optional[Callback] = None) -> "RealtimeChannel":
        return self.on("broadcast", {"event": event}, callback or (lambda _p: None))

    def on_presence_sync(self, *, callback: Optional[Callback] = None) -> "RealtimeChannel":
        return self.on("presence", {"event": "sync"}, callback or (lambda _p: None))

    def on_presence_join(self, *, callback: Optional[Callback] = None) -> "RealtimeChannel":
        return self.on("presence", {"event": "join"}, callback or (lambda _p: None))

    def on_presence_leave(self, *, callback: Optional[Callback] = None) -> "RealtimeChannel":
        return self.on("presence", {"event": "leave"}, callback or (lambda _p: None))

    # ─── lifecycle ────────────────────────────────────────────────────

    def subscribe(self, callback: Optional[StatusCallback] = None) -> "RealtimeChannel":
        """Join the channel; ``callback(status, error)`` gets SUBSCRIBED or CHANNEL_ERROR."""
        self._wanted = True
        self._status_cb = callback
        self._client._join(self)
        return self

    def unsubscribe(self) -> None:
        self._wanted = False
        if self._status != "CLOSED":
            self._client._push(self.topic, "phx_leave", {})
        self._set_status("CLOSED")

    def _join_payload(self) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {
            "broadcast": self._config.get("broadcast") or {"self": False, "ack": False},
            "presence": self._config.get("presence") or {"key": ""},
            "postgres_changes": [
                {k: v for k, v in {
                    "event": b["filter"].get("event", "*"),
                    "schema": b["filter"].get("schema", "public"),
                    "table": b["filter"].get("table"),
                    "filter": b["filter"].get("filter"),
                }.items() if v is not None}
                for b in self._bindings if b["type"] == "postgres_changes"
            ],
        }
        payload: Dict[str, Any] = {"config": cfg}
        if self._client._access_token:
            payload["access_token"] = self._client._access_token
        return payload

    def _set_status(self, status: str, err: Optional[Exception] = None) -> None:
        changed = status != self._status
        self._status = status
        if changed and self._status_cb and status in ("SUBSCRIBED", "CHANNEL_ERROR", "TIMED_OUT"):
            try:
                self._status_cb(status, err)
            except Exception:
                pass

    # ─── sending ──────────────────────────────────────────────────────

    def send(self, message: Dict[str, Any]) -> None:
        """Send ``{"type": "broadcast", "event": ..., "payload": ...}`` (JS ``send``)."""
        if message.get("type", "broadcast") != "broadcast":
            return
        self._client._push(self.topic, "broadcast",
                           {"type": "broadcast", "event": message.get("event"), "payload": message.get("payload") or {}})

    def send_broadcast(self, event: str, payload: Dict[str, Any]) -> None:
        self.send({"type": "broadcast", "event": event, "payload": payload})

    def track(self, payload: Dict[str, Any]) -> None:
        """Share this client's presence state on the channel."""
        self._client._push(self.topic, "presence", {"type": "presence", "event": "track", "payload": payload})

    def untrack(self) -> None:
        self._client._push(self.topic, "presence", {"type": "presence", "event": "untrack"})

    def presence_state(self) -> Dict[str, List[Dict[str, Any]]]:
        """Presence by key: ``{key: [meta, ...]}`` (JS ``presenceState_()``)."""
        return {k: list(v) for k, v in self._presence.items()}

    # ─── receiving ────────────────────────────────────────────────────

    def _emit(self, type: str, match: Callable[[Dict[str, Any]], bool], payload: Any) -> None:
        for b in list(self._bindings):
            if b["type"] == type and match(b["filter"]):
                try:
                    b["callback"](payload)
                except Exception:
                    pass

    def _handle(self, event: str, payload: Any, ref: Optional[str]) -> None:
        payload = payload if isinstance(payload, dict) else {}
        if event == "phx_reply" and ref is not None and ref == self._join_ref:
            if payload.get("status") == "ok":
                self._set_status("SUBSCRIBED")
            else:
                resp = payload.get("response") or {}
                self._set_status("CHANNEL_ERROR", Exception(str(resp.get("reason") or resp or "join refused")))
        elif event in ("phx_error", "phx_close"):
            self._set_status("CHANNEL_ERROR" if event == "phx_error" else "CLOSED")
        elif event == "postgres_changes":
            data = payload.get("data") or {}
            change = {
                "eventType": data.get("type"),
                "schema": data.get("schema"),
                "table": data.get("table"),
                "commit_timestamp": data.get("commit_timestamp"),
                "new": data.get("record") or {},
                "old": data.get("old_record") or {},
                "errors": data.get("errors"),
            }

            def pg_match(f: Dict[str, Any]) -> bool:
                return (f.get("event", "*") in ("*", change["eventType"])
                        and f.get("schema", "*") in ("*", change["schema"])
                        and f.get("table", "*") in ("*", change["table"]))

            self._emit("postgres_changes", pg_match, change)
        elif event == "broadcast":
            ev = payload.get("event")
            msg = {"type": "broadcast", "event": ev, "payload": payload.get("payload")}
            self._emit("broadcast", lambda f: f.get("event", "*") in ("*", ev), msg)
        elif event == "presence_state":
            self._presence = {k: list((v or {}).get("metas") or []) for k, v in payload.items()}
            self._emit("presence", lambda f: f.get("event") == "sync", self.presence_state())
        elif event == "presence_diff":
            joins = payload.get("joins") or {}
            leaves = payload.get("leaves") or {}
            for k, v in joins.items():
                self._presence.setdefault(k, []).extend((v or {}).get("metas") or [])
            for k, v in leaves.items():
                gone = {m.get("phx_ref") for m in (v or {}).get("metas") or []}
                left = [m for m in self._presence.get(k, []) if m.get("phx_ref") not in gone]
                if left:
                    self._presence[k] = left
                else:
                    self._presence.pop(k, None)
            diff = {"type": "presence_diff", "presenceState": self.presence_state(), "joins": joins, "leaves": leaves}
            if joins:
                self._emit("presence", lambda f: f.get("event") == "join", diff)
            if leaves:
                self._emit("presence", lambda f: f.get("event") == "leave", diff)
            self._emit("presence", lambda f: f.get("event") == "sync", self.presence_state())


class AfribaseRealtimeClient:
    """WebSocket realtime client. Prefer ``client.channel()``."""

    def __init__(
        self,
        url: str,
        api_key: str,
        access_token: Optional[str] = None,
        *,
        ws_factory: Optional[Callable[[str], Any]] = None,
        heartbeat_interval: float = HEARTBEAT_S,
    ) -> None:
        self._url = url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        self._api_key = api_key
        self._access_token = access_token
        self._channels: Dict[str, RealtimeChannel] = {}
        self._ws: Any = None
        self._ws_factory = ws_factory
        self._heartbeat_interval = heartbeat_interval
        self._lock = threading.RLock()
        self._ref = 0
        self._pending: List[str] = []  # frames sent before the socket opened
        self._connected = False
        self._closing = False
        self._reconnects = 0
        self._stop = threading.Event()

    # ─── public API ───────────────────────────────────────────────────

    def endpoint_url(self) -> str:
        params = {"apikey": self._api_key, "vsn": "1.0.0"}
        if self._access_token:
            params["token"] = self._access_token
        return f"{self._url}/realtime/v1/websocket?{urlencode(params)}"

    def set_auth(self, access_token: Optional[str]) -> None:
        """Use a new access token; joined channels get it at once (like JS ``setAuth``)."""
        self._access_token = access_token
        if self._connected:
            for ch in list(self._channels.values()):
                if ch.status == "SUBSCRIBED":
                    self._push(ch.topic, "access_token", {"access_token": access_token})

    def channel(self, name: str, config: Optional[Dict[str, Any]] = None) -> RealtimeChannel:
        """Create or get a channel; ``config`` = ``{"broadcast": {"self", "ack"}, "presence": {"key"}}``."""
        topic = _topic(name)
        with self._lock:
            if topic not in self._channels:
                self._channels[topic] = RealtimeChannel(name, self, config)
            return self._channels[topic]

    def get_channels(self) -> List[RealtimeChannel]:
        return list(self._channels.values())

    def remove_channel(self, channel: RealtimeChannel) -> None:
        channel.unsubscribe()
        with self._lock:
            self._channels.pop(channel.topic, None)
            empty = not self._channels
        if empty:
            self.disconnect()

    def remove_all_channels(self) -> None:
        """Leave every channel and disconnect."""
        for ch in list(self._channels.values()):
            ch.unsubscribe()
        with self._lock:
            self._channels.clear()
        self.disconnect()

    def disconnect(self) -> None:
        self._closing = True
        self._stop.set()
        self._connected = False
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    # Older name.
    _disconnect = disconnect

    # ─── internals ────────────────────────────────────────────────────

    def _next_ref(self) -> str:
        with self._lock:
            self._ref += 1
            return str(self._ref)

    def _push(self, topic: str, event: str, payload: Dict[str, Any], ref: Optional[str] = None) -> str:
        ref = ref or self._next_ref()
        frame = _json.dumps({"topic": topic, "event": event, "payload": payload, "ref": ref})
        with self._lock:
            ws = self._ws if self._connected else None
            if ws is None:
                if event != "heartbeat":
                    self._pending.append(frame)
                return ref
        try:
            ws.send(frame)
        except Exception:
            with self._lock:
                self._pending.append(frame)
        return ref

    def _join(self, channel: RealtimeChannel) -> None:
        if not self._connected and not self._connect():
            channel._set_status("CHANNEL_ERROR", Exception("could not connect to realtime"))
            return
        channel._status = "JOINING"
        channel._join_ref = self._next_ref()
        self._push(channel.topic, "phx_join", channel._join_payload(), ref=channel._join_ref)

    def _open(self) -> Any:
        if self._ws_factory is not None:
            return self._ws_factory(self.endpoint_url())
        import websockets.sync.client as ws_sync

        return ws_sync.connect(self.endpoint_url())

    def _connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            try:
                ws = self._open()
            except Exception:
                return False
            self._ws = ws
            self._connected = True
            self._closing = False
            self._stop = threading.Event()
            pending, self._pending = self._pending, []
        for frame in pending:
            try:
                ws.send(frame)
            except Exception:
                pass
        stop = self._stop
        threading.Thread(target=self._read_loop, args=(ws, stop), daemon=True, name="afribase-realtime").start()
        threading.Thread(target=self._heartbeat_loop, args=(stop,), daemon=True, name="afribase-heartbeat").start()
        return True

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        while not stop.wait(self._heartbeat_interval):
            if self._connected:
                self._push("phoenix", "heartbeat", {})

    def _read_loop(self, ws: Any, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                raw = ws.recv()
            except Exception:
                break
            self._dispatch(raw)
        if stop.is_set() or self._closing:
            return
        self._on_dropped(ws)

    def _dispatch(self, raw: Any) -> None:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        try:
            msg = _json.loads(raw)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        ch = self._channels.get(str(msg.get("topic", "")))
        if ch is not None:
            ch._handle(str(msg.get("event", "")), msg.get("payload"), msg.get("ref"))

    def _on_dropped(self, ws: Any) -> None:
        """Reconnects with backoff (1 s, 2 s, ... 30 s, at most 10 tries) and rejoins channels."""
        with self._lock:
            if self._ws is not ws:
                return
            self._connected = False
            self._ws = None
            self._stop.set()
        for ch in self._channels.values():
            if ch._wanted:
                ch._status = "CLOSED"
        while self._reconnects < MAX_RECONNECTS and not self._closing:
            delay = min(1.0 * (2 ** self._reconnects), 30.0)
            self._reconnects += 1
            if threading.Event().wait(delay if self._ws_factory is None else 0.01) or self._closing:
                return
            if self._connect():
                self._reconnects = 0
                for ch in list(self._channels.values()):
                    if ch._wanted:
                        self._join(ch)
                return
