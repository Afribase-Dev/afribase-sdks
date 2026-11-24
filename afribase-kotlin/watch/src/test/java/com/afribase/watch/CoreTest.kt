package com.afribase.watch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class JsonTest {
    @Test
    fun writesValuesAndEscapes() {
        val s = Json.write(linkedMapOf("a" to "q\"\\\n\u0001", "n" to 3, "f" to 1.5f, "d" to 2.0, "b" to true, "skip" to null, "l" to listOf(1, "x")))
        assertEquals("{\"a\":\"q\\\"\\\\\\n\\u0001\",\"n\":3,\"f\":1.5,\"d\":2,\"b\":true,\"l\":[1,\"x\"]}", s)
    }

    @Test
    fun explicitNullAndRaw() {
        assertEquals("{\"x\":null,\"r\":{\"k\":1}}", Json.write(linkedMapOf("x" to JsonNull, "r" to RawJson("{\"k\":1}"))))
    }

    @Test
    fun roundsFloatsToTwoDecimals() {
        val sb = StringBuilder()
        Json.number(sb, 120.456)
        assertEquals("120.46", sb.toString())
    }
}

class UrlsTest {
    @Test
    fun subURLMatchesJs() {
        assertEquals("https://a/watch/ingest/replay?key=abw_1", Urls.sub("https://a/watch/ingest", "replay", "abw_1"))
        assertEquals("https://a/watch/ingest/presence?x=y&key=k%2B", Urls.sub("https://a/watch/ingest/?x=y", "presence", "k+"))
        assertEquals("https://a/watch/ingest?key=k", Urls.ingest("https://a/watch/ingest", "k"))
        assertEquals("https://a/p", Urls.stripQuery("https://a/p?token=1#x"))
    }

    @Test
    fun deliveryRules() {
        assertTrue(deliveredOrRejected(202))
        assertTrue(deliveredOrRejected(400))
        assertTrue(deliveredOrRejected(403))
        assertFalse(deliveredOrRejected(429))
        assertFalse(deliveredOrRejected(503))
        assertFalse(deliveredOrRejected(-1))
    }
}

class EventBuilderTest {
    private val env = EventEnv("1.0", "prod", "Android 15", "Google Pixel 8", "0.1.0")

    @Test
    fun errorEventHasTheIngestShape() {
        val ev = EventBuilder.error(
            IllegalStateException("boom"), fatal = true, thread = "main", env = env, sessionId = "s1",
            userId = "u1", screen = "CheckoutActivity", crumbs = listOf(mapOf("t" to 1L, "type" to "click")),
            context = mapOf("orderId" to "o1"), now = 0L,
        )
        assertEquals("error", ev["kind"])
        assertEquals("java.lang.IllegalStateException: boom", ev["message"])
        assertEquals("app://CheckoutActivity", ev["url"])
        assertEquals("s1", ev["sessionId"])
        assertEquals("u1", ev["userId"])
        assertEquals("1.0", ev["release"])
        assertEquals("prod", ev["environment"])
        assertEquals("android", ev["platform"])
        assertEquals("1970-01-01T00:00:00.000Z", ev["timestamp"])
        assertTrue((ev["stack"] as String).contains("IllegalStateException"))
        @Suppress("UNCHECKED_CAST")
        val ctx = ev["context"] as Map<String, Any?>
        assertEquals(true, ctx["fatal"])
        assertEquals("main", ctx["thread"])
        assertEquals("o1", ctx["orderId"])
        assertEquals("Android 15", ctx["os"])
        // Every key the server reads (service.WatchIngestEvent) uses its JSON name.
        val known = setOf("kind", "message", "stack", "url", "method", "status", "durationMs", "release", "environment", "userId", "sessionId", "breadcrumbs", "context", "timestamp", "platform")
        assertTrue(known.containsAll(ev.keys))
    }

    @Test
    fun capsMessage() {
        val ev = EventBuilder.error(RuntimeException("x".repeat(5000)), false, null, env, "s", null, null, emptyList(), null, 0L)
        assertEquals(EventBuilder.MAX_MESSAGE, (ev["message"] as String).length)
        assertEquals("app://unknown", ev["url"])
    }

    @Test
    fun batchWrapsEvents() {
        assertEquals("{\"events\":[{\"a\":1},{\"b\":2}]}", EventBuilder.batch(listOf("{\"a\":1}", "{\"b\":2}")))
    }

    @Test
    fun breadcrumbsKeepLast30() {
        val b = Breadcrumbs()
        repeat(40) { b.add("click", mapOf("i" to it), t = it.toLong()) }
        val s = b.snapshot()
        assertEquals(30, s.size)
        assertEquals(10, s.first()["i"])
        assertEquals("click", s.first()["type"])
    }

    @Test
    fun breadcrumbValuesMaskedOneByOne() {
        val b = Breadcrumbs()
        b.add("fetch", linkedMapOf("url" to "https://api.x/pay?token=abc#f", "status" to 500, "ms" to 1234L,
            "password" to "hunter2", "apiKey" to 12345, "el" to mapOf("tag" to "Button", "authToken" to "t0k")), t = 1763578963123L)
        val json = Json.write(b.snapshot())
        assertTrue(json, json.contains("\"t\":1763578963123"))
        assertTrue(json.contains("\"url\":\"https://api.x/pay\""))
        assertTrue(json.contains("\"status\":500"))
        assertTrue(json.contains("\"ms\":1234"))
        assertTrue(json.contains("\"password\":\"${CrumbMask.DOTS}\""))
        assertTrue(json.contains("\"apiKey\":\"${CrumbMask.DOTS}\""))
        assertTrue(json.contains("\"authToken\":\"${CrumbMask.DOTS}\""))
        assertFalse(json.contains("hunter2") || json.contains("abc") || json.contains("t0k"))
    }
}

class EventStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun savesListsAndTrims() {
        val store = EventStore(tmp.newFolder("ev"), maxFiles = 3, suffix = ".json")
        repeat(5) { store.save("{\"i\":$it}".toByteArray()) }
        val files = store.list()
        assertEquals(3, files.size)
        assertEquals("{\"i\":2}", String(store.read(files.first())!!))
        store.delete(files.first())
        assertEquals(2, store.list().size)
    }

    @Test
    fun survivesANewInstance() {
        val dir = tmp.newFolder("ev2")
        EventStore(dir, 10, ".json").save("{}".toByteArray())
        assertEquals(1, EventStore(dir, 10, ".json").list().size)
        assertNull(EventStore(dir, 10, ".json").read(java.io.File(dir, "missing")))
    }
}
