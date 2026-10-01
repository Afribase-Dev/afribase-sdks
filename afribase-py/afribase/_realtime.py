"""AfribaseRealtimeClient — WebSocket-based realtime subscriptions."""

from __future__ import annotations

import json as _json
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class RealtimeChannel:
    """A single realtime channel that supports postgres_changes, broadcast, and presence.

    Usage::

        channel = client.channel("room1")
        channel.on_postgres_changes("INSERT", schema="public", table="messages",
                                     callback=lambda payload: print(payload))
        channel.on_broadcast("typing", callback=lambda payload: print(payload))
        channel.on_presence_sync(callback=lambda state: print(state))
        channel.subscribe()
    """

    def __init__(self, name: str, client: "AfribaseRealtimeClient") -> None:
        self.name = name
        self._client = client
        self._bindings: List[Dict[str, Any]] = []
        self._subscribed = False

    def on_postgres_changes(
        self,
        event: str,
        *,
        schema: str = "public",
        table: Optional[str] = None,
        filter: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "RealtimeChannel":
        """Listen for Postgres row-level changes."""
        self._bindings.append({
            "type": "postgres_changes",
            "event": event,
            "schema": schema,
            "table": table,
            "filter": filter,
            "callback": callback,
        })
        return self

    def on_broadcast(
        self,
        event: str,
        *,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "RealtimeChannel":
        """Listen for broadcast messages."""
        self._bindings.append({
            "type": "broadcast",
            "event": event,
            "callback": callback,
        })
        return self

    def on_presence_sync(
        self,
        *,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "RealtimeChannel":
        """Listen for presence sync events."""
        self._bindings.append({
            "type": "presence",
            "event": "sync",
            "callback": callback,
        })
        return self

    def on_presence_join(
        self,
        *,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "RealtimeChannel":
        self._bindings.append({
            "type": "presence",
            "event": "join",
            "callback": callback,
        })
        return self

    def on_presence_leave(
        self,
        *,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "RealtimeChannel":
        self._bindings.append({
            "type": "presence",
            "event": "leave",
            "callback": callback,
        })
        return self

    def subscribe(
        self,
        callback: Optional[Callable[[str, Optional[Exception]], None]] = None,
    ) -> "RealtimeChannel":
        """Subscribe to this channel's events."""
        self._subscribed = True
        self._client._subscribe_channel(self)
        if callback:
            callback("SUBSCRIBED", None)
        return self

    def unsubscribe(self) -> None:
        """Unsubscribe from this channel."""
        self._subscribed = False
        self._client._unsubscribe_channel(self)

    def send_broadcast(self, event: str, payload: Dict[str, Any]) -> None:
        """Send a broadcast message to the channel."""
        self._client._send(self.name, {
            "type": "broadcast",
            "event": event,
            "payload": payload,
        })

    def track(self, payload: Dict[str, Any]) -> None:
        """Track presence for this channel."""
        self._client._send(self.name, {
            "type": "presence",
            "event": "track",
            "payload": payload,
        })

    def untrack(self) -> None:
        """Remove presence tracking."""
        self._client._send(self.name, {
            "type": "presence",
            "event": "untrack",
        })

    def _dispatch(self, message: Dict[str, Any]) -> None:
        """Dispatch a received message to matching callbacks."""
        msg_type = message.get("type", "")
        msg_event = message.get("event", "")
        for binding in self._bindings:
            if binding["type"] == msg_type:
                if binding.get("event") in (msg_event, "*"):
                    cb = binding.get("callback")
                    if cb:
                        try:
                            cb(message.get("payload", message))
                        except Exception:
                            pass


class AfribaseRealtimeClient:
    """WebSocket-based realtime client for Afribase.

    Supports postgres_changes, broadcast, and presence.

    Usage::

        channel = client.channel("room1")
        channel.on_broadcast("message", callback=lambda p: print(p))
        channel.subscribe()
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        access_token: Optional[str] = None,
    ) -> None:
        self._url = url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        self._api_key = api_key
        self._access_token = access_token
        self._channels: Dict[str, RealtimeChannel] = {}
        self._ws: Any = None
        self._ws_thread: Optional[threading.Thread] = None
        self._connected = False
        self._heartbeat_ref = 0

    def set_auth(self, access_token: Optional[str]) -> None:
        """Update the access token (called when auth state changes)."""
        self._access_token = access_token

    def channel(self, name: str) -> RealtimeChannel:
        """Create or get a realtime channel."""
        if name not in self._channels:
            self._channels[name] = RealtimeChannel(name, self)
        return self._channels[name]

    def remove_channel(self, channel: RealtimeChannel) -> None:
        """Remove a channel."""
        channel.unsubscribe()
        self._channels.pop(channel.name, None)

    def remove_all_channels(self) -> None:
        """Remove all channels and disconnect."""
        for ch in list(self._channels.values()):
            ch._subscribed = False
        self._channels.clear()
        self._disconnect()

    # ─── Internal ─────────────────────────────────────────────────────

    def _subscribe_channel(self, channel: RealtimeChannel) -> None:
        """Connect if needed and subscribe a channel."""
        if not self._connected:
            self._connect()
        self._send(channel.name, {
            "type": "phx_join",
            "topic": f"realtime:{channel.name}",
            "payload": {
                "config": {
                    "postgres_changes": [
                        {
                            "event": b.get("event", "*"),
                            "schema": b.get("schema", "public"),
                            "table": b.get("table", "*"),
                            "filter": b.get("filter"),
                        }
                        for b in channel._bindings
                        if b["type"] == "postgres_changes"
                    ]
                }
            },
            "ref": str(self._heartbeat_ref),
        })
        self._heartbeat_ref += 1

    def _unsubscribe_channel(self, channel: RealtimeChannel) -> None:
        self._send(channel.name, {
            "type": "phx_leave",
            "topic": f"realtime:{channel.name}",
            "payload": {},
            "ref": str(self._heartbeat_ref),
        })
        self._heartbeat_ref += 1

    def _connect(self) -> None:
        """Establish a WebSocket connection in a background thread."""
        try:
            import websockets.sync.client as ws_sync  # type: ignore[import-untyped]
        except ImportError:
            # Graceful fallback: realtime won't work but SDK won't crash
            return

        ws_url = f"{self._url}/realtime/v1/websocket?apikey={self._api_key}&vsn=1.0.0"
        if self._access_token:
            ws_url += f"&token={self._access_token}"

        try:
            self._ws = ws_sync.connect(ws_url)
            self._connected = True

            def _listen() -> None:
                try:
                    while self._connected and self._ws:
                        try:
                            raw = self._ws.recv(timeout=30)
                            msg = _json.loads(raw) if isinstance(raw, str) else {}
                            topic = msg.get("topic", "")
                            # Strip "realtime:" prefix
                            channel_name = topic.replace("realtime:", "")
                            ch = self._channels.get(channel_name)
                            if ch:
                                ch._dispatch(msg.get("payload", msg))
                        except Exception:
                            if not self._connected:
                                break
                            time.sleep(1)
                except Exception:
                    pass

            self._ws_thread = threading.Thread(target=_listen, daemon=True)
            self._ws_thread.start()
        except Exception:
            self._connected = False

    def _disconnect(self) -> None:
        self._connected = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _send(self, channel_name: str, message: Dict[str, Any]) -> None:
        if not self._ws or not self._connected:
            return
        try:
            self._ws.send(_json.dumps(message))
        except Exception:
            pass
