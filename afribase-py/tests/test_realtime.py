import json
import queue
import threading
import time

from afribase import create_client
from afribase._realtime import AfribaseRealtimeClient


class FakeWS:
    def __init__(self, url):
        self.url = url
        self.sent = []
        self.inbox = queue.Queue()
        self.closed = False

    def send(self, frame):
        self.sent.append(json.loads(frame))

    def recv(self):
        item = self.inbox.get()
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True
        self.inbox.put(ConnectionError("closed"))

    def feed(self, **frame):
        self.inbox.put(json.dumps(frame))


def wait(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def make(token=None, **kw):
    sockets = []

    def factory(url):
        ws = FakeWS(url)
        sockets.append(ws)
        return ws

    rt = AfribaseRealtimeClient("https://p.afribase.dev", "anon key", token, ws_factory=factory, **kw)
    return rt, sockets


def test_url_join_frame_and_status():
    rt, socks = make("tok&1")
    statuses = []
    ch = rt.channel("room1", config={"broadcast": {"self": True, "ack": False}, "presence": {"key": "u1"}})
    ch.on("postgres_changes", {"event": "INSERT", "schema": "public", "table": "msgs"}, lambda p: None)
    ch.subscribe(lambda s, e: statuses.append(s))
    ws = socks[0]
    assert ws.url.startswith("wss://p.afribase.dev/realtime/v1/websocket?")
    assert "apikey=anon+key" in ws.url and "token=tok%261" in ws.url and "vsn=1.0.0" in ws.url
    join = ws.sent[0]
    assert join["topic"] == "realtime:room1" and join["event"] == "phx_join"
    cfg = join["payload"]["config"]
    assert cfg["broadcast"] == {"self": True, "ack": False}
    assert cfg["presence"] == {"key": "u1"}
    assert cfg["postgres_changes"] == [{"event": "INSERT", "schema": "public", "table": "msgs"}]
    assert join["payload"]["access_token"] == "tok&1"
    assert ch.status == "JOINING"
    ws.feed(topic="realtime:room1", event="phx_reply", payload={"status": "ok", "response": {}}, ref=join["ref"])
    assert wait(lambda: ch.status == "SUBSCRIBED")
    assert statuses == ["SUBSCRIBED"]
    rt.disconnect()


def test_topic_not_double_prefixed():
    rt, _ = make()
    assert rt.channel("realtime:a").topic == "realtime:a"
    assert rt.channel("a") is rt.channel("realtime:a")
    assert rt.channel("realtime:realtime:x").topic == "realtime:realtime:x"


def test_join_refused_reports_channel_error():
    rt, socks = make()
    got = []
    ch = rt.channel("r").subscribe(lambda s, e: got.append((s, str(e))))
    ref = socks[0].sent[0]["ref"]
    socks[0].feed(topic="realtime:r", event="phx_reply", payload={"status": "error", "response": {"reason": "nope"}}, ref=ref)
    assert wait(lambda: ch.status == "CHANNEL_ERROR")
    assert got == [("CHANNEL_ERROR", "nope")]
    rt.disconnect()


def test_connect_failure_is_channel_error():
    def boom(url):
        raise OSError("down")

    rt = AfribaseRealtimeClient("http://x", "k", ws_factory=boom)
    got = []
    ch = rt.channel("r").subscribe(lambda s, e: got.append(s))
    assert ch.status == "CHANNEL_ERROR" and got == ["CHANNEL_ERROR"]


def test_postgres_dispatch_filters():
    rt, socks = make()
    ins, anyt, other = [], [], []
    ch = rt.channel("db")
    ch.on("postgres_changes", {"event": "INSERT", "schema": "public", "table": "msgs"}, ins.append)
    ch.on("postgres_changes", {"event": "*", "schema": "public"}, anyt.append)
    ch.on("postgres_changes", {"event": "DELETE", "schema": "public", "table": "msgs"}, other.append)
    ch.subscribe()
    socks[0].feed(topic="realtime:db", event="postgres_changes", ref=None, payload={"data": {
        "type": "INSERT", "schema": "public", "table": "msgs", "record": {"id": 1}, "commit_timestamp": "t"}})
    assert wait(lambda: len(anyt) == 1)
    assert ins[0]["new"] == {"id": 1} and ins[0]["eventType"] == "INSERT" and ins[0]["old"] == {}
    assert other == []
    rt.disconnect()


def test_broadcast_send_and_receive():
    rt, socks = make()
    got = []
    ch = rt.channel("chat").on("broadcast", {"event": "typing"}, got.append).subscribe()
    ch.send({"type": "broadcast", "event": "typing", "payload": {"who": "a"}})
    ch.send_broadcast("typing", {"who": "b"})
    frames = [f for f in socks[0].sent if f["event"] == "broadcast"]
    assert frames[0]["topic"] == "realtime:chat"
    assert frames[0]["payload"] == {"type": "broadcast", "event": "typing", "payload": {"who": "a"}}
    assert frames[1]["payload"]["payload"] == {"who": "b"}
    socks[0].feed(topic="realtime:chat", event="broadcast", ref=None,
                  payload={"type": "broadcast", "event": "typing", "payload": {"who": "z"}})
    socks[0].feed(topic="realtime:chat", event="broadcast", ref=None,
                  payload={"type": "broadcast", "event": "other", "payload": {}})
    assert wait(lambda: len(got) == 1)
    time.sleep(0.05)
    assert got == [{"type": "broadcast", "event": "typing", "payload": {"who": "z"}}]
    rt.disconnect()


def test_presence_track_state_and_diff():
    rt, socks = make()
    syncs, joins, leaves = [], [], []
    ch = rt.channel("lobby", config={"presence": {"key": "u1"}})
    ch.on("presence", {"event": "sync"}, syncs.append)
    ch.on_presence_join(callback=joins.append)
    ch.on_presence_leave(callback=leaves.append)
    ch.subscribe()
    ch.track({"online": True})
    ch.untrack()
    pres = [f for f in socks[0].sent if f["event"] == "presence"]
    assert pres[0] == {"topic": "realtime:lobby", "event": "presence", "ref": pres[0]["ref"],
                       "payload": {"type": "presence", "event": "track", "payload": {"online": True}}}
    assert pres[1]["payload"] == {"type": "presence", "event": "untrack"}
    ws = socks[0]
    ws.feed(topic="realtime:lobby", event="presence_state", ref=None,
            payload={"u1": {"metas": [{"phx_ref": "a", "online": True}]}})
    assert wait(lambda: len(syncs) == 1)
    assert ch.presence_state() == {"u1": [{"phx_ref": "a", "online": True}]}
    ws.feed(topic="realtime:lobby", event="presence_diff", ref=None,
            payload={"joins": {"u2": {"metas": [{"phx_ref": "b"}]}}, "leaves": {"u1": {"metas": [{"phx_ref": "a"}]}}})
    assert wait(lambda: len(leaves) == 1)
    assert len(joins) == 1
    assert ch.presence_state() == {"u2": [{"phx_ref": "b"}]}
    rt.disconnect()


def test_set_auth_pushes_token_to_joined_channels():
    rt, socks = make()
    ch = rt.channel("r").subscribe()
    socks[0].feed(topic="realtime:r", event="phx_reply", payload={"status": "ok"}, ref=socks[0].sent[0]["ref"])
    assert wait(lambda: ch.status == "SUBSCRIBED")
    rt.set_auth("new")
    f = socks[0].sent[-1]
    assert f["topic"] == "realtime:r" and f["event"] == "access_token" and f["payload"] == {"access_token": "new"}
    rt.disconnect()


def test_heartbeat():
    rt, socks = make(heartbeat_interval=0.02)
    rt.channel("r").subscribe()
    assert wait(lambda: any(f["event"] == "heartbeat" and f["topic"] == "phoenix" for f in socks[0].sent))
    rt.disconnect()


def test_reconnect_rejoins():
    rt, socks = make()
    ch = rt.channel("r").subscribe()
    socks[0].inbox.put(ConnectionError("drop"))
    assert wait(lambda: len(socks) == 2 and socks[1].sent)
    assert socks[1].sent[0]["event"] == "phx_join" and socks[1].sent[0]["topic"] == "realtime:r"
    assert ch.status == "JOINING"
    rt.disconnect()


def test_unsubscribe_and_remove_all():
    rt, socks = make()
    a = rt.channel("a").subscribe()
    rt.channel("b").subscribe()
    rt.remove_all_channels()
    leaves = [f["topic"] for f in socks[0].sent if f["event"] == "phx_leave"]
    assert leaves == ["realtime:a", "realtime:b"]
    assert a.status == "CLOSED" and socks[0].closed and rt.get_channels() == []


def test_client_channel_passes_config():
    client = create_client("https://p.afribase.dev", "anon")
    ch = client.channel("room", config={"broadcast": {"self": True}})
    assert ch._join_payload()["config"]["broadcast"] == {"self": True}
