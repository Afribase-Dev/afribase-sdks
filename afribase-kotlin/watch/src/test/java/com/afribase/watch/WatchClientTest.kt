package com.afribase.watch

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.concurrent.TimeUnit

private typealias FakeTransport = RecordingTransport

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WatchClientTest {
    private val app: Application = ApplicationProvider.getApplicationContext()
    private val config = WatchConfig(key = "abw_test", endpoint = "https://api.test/watch/ingest", release = "1.0", live = false)

    @After
    fun tearDown() {
        AfribaseWatch.stop()
    }

    private fun waitFor(timeoutMs: Long = 5000, cond: () -> Boolean) {
        val end = System.currentTimeMillis() + timeoutMs
        while (!cond() && System.currentTimeMillis() < end) Thread.sleep(20)
    }

    @Test
    fun capturedExceptionReachesIngest() {
        val t = FakeTransport()
        val c = WatchClient(app, config, t)
        c.start()
        c.captureError(IllegalStateException("boom"), mapOf("orderId" to "o1"))
        c.flush()
        waitFor { t.posts.any { it.second.contains("boom") } }
        val (url, body) = t.posts.first { it.second.contains("boom") }
        assertEquals("https://api.test/watch/ingest?key=abw_test", url)
        assertTrue(body, body.startsWith("{\"events\":[{\"kind\":\"error\""))
        assertTrue(body.contains("\"sessionId\":\"${c.sessionId}\""))
        assertTrue(body.contains("\"platform\":\"android\""))
        c.stop()
    }

    @Test
    fun eventsSurviveAFailedSendAndADeadProcess() {
        val down = FakeTransport(code = -1)
        val c1 = WatchClient(app, config, down)
        c1.start()
        c1.captureError(RuntimeException("kept on disk"), null)
        c1.flush()
        waitFor { down.posts.isNotEmpty() }
        c1.stop()

        // "Next launch": a new client finds and sends it.
        val up = FakeTransport()
        val c2 = WatchClient(app, config, up)
        c2.start()
        waitFor { up.posts.any { it.second.contains("kept on disk") } }
        assertTrue(up.posts.any { it.second.contains("kept on disk") })
        c2.stop()
    }

    @Test
    fun crashHandlerPersistsAndChains() {
        val t = FakeTransport(code = -1)
        var chained: Throwable? = null
        val previous = Thread.UncaughtExceptionHandler { _, e -> chained = e }
        Thread.setDefaultUncaughtExceptionHandler(previous)
        val c = WatchClient(app, config, t)
        c.start()
        val boom = RuntimeException("fatal boom")
        Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(Thread.currentThread(), boom)
        assertTrue(chained === boom)
        c.stop()
        assertTrue(Thread.getDefaultUncaughtExceptionHandler() === previous)

        val up = FakeTransport()
        val c2 = WatchClient(app, config, up)
        c2.start()
        waitFor { up.posts.any { it.second.contains("fatal boom") } }
        val body = up.posts.first { it.second.contains("fatal boom") }.second
        assertTrue(body, body.contains("\"fatal\":true"))
        c2.stop()
    }

    @Test
    fun interceptorAddsSessionHeader() {
        AfribaseWatch.init(app, config)
        val sid = AfribaseWatch.sessionId
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200))
        server.start()
        try {
            OkHttpClient.Builder().addInterceptor(WatchInterceptor()).build()
                .newCall(Request.Builder().url(server.url("/api/pay?card=1")).build()).execute().close()
            val req = server.takeRequest(5, TimeUnit.SECONDS)!!
            assertEquals(sid, req.getHeader("X-Watch-Session"))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun batchesAtMost50EventsPerRequest() {
        val t = FakeTransport(code = -1)
        val c = WatchClient(app, config, t)
        c.start()
        repeat(60) { c.captureError(RuntimeException("e$it"), null) }
        c.flush()
        waitFor { t.posts.isNotEmpty() }
        t.code = 202
        c.flush()
        waitFor { t.posts.count { it.second.contains("e59") || it.second.contains("e0\"") } >= 2 || t.posts.size >= 4 }
        Thread.sleep(300)
        for ((_, body) in t.posts) {
            assertTrue(Regex("\"kind\":").findAll(body).count() <= 50)
            assertTrue(body.length <= 256 * 1024)
        }
        val ok = t.posts.drop(t.posts.indexOfFirst { true } + 1)
        assertTrue(ok.joinToString().contains("e59"))
        c.stop()
    }

    @Test
    fun sampleRateZeroDropsErrorsButNotOtherKinds() {
        val t = FakeTransport()
        val c = WatchClient(app, config.copy(sampleRate = 0.0), t)
        c.start()
        c.captureError(RuntimeException("sampled out"), null)
        c.log("kept", null)
        c.flush()
        waitFor { t.posts.any { it.second.contains("kept") } }
        assertTrue(t.posts.none { it.second.contains("sampled out") })
        c.stop()
    }

    @Test
    fun interceptorReportsFailedAndServerErrors() {
        AfribaseWatch.init(app, config)
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(503))
        server.start()
        try {
            OkHttpClient.Builder().addInterceptor(WatchInterceptor()).build()
                .newCall(Request.Builder().url(server.url("/api/pay?card=4242")).build()).execute().close()
        } finally {
            server.shutdown()
        }
        AfribaseWatch.flush()
        Thread.sleep(500)
        // Sent through the real transport to a host that does not exist: check the queue on disk instead.
        val dir = java.io.File(app.filesDir, "afribase-watch/events")
        val stored = (dir.listFiles() ?: emptyArray()).joinToString { it.readText() }
        assertTrue(stored, stored.contains("\"kind\":\"http\""))
        assertTrue(stored.contains("-> 503"))
        assertFalse(stored.contains("4242"))
    }

    @Test
    fun noopBeforeInit() {
        AfribaseWatch.stop()
        assertNull(AfribaseWatch.sessionId)
        AfribaseWatch.captureException(RuntimeException("ignored"))
    }
}

class PresenceBodyTest {
    @Test
    fun bodyShape() {
        val exec = java.util.concurrent.Executors.newSingleThreadScheduledExecutor()
        val p = Presence("u", "abw_1", "1.0", { "sid" }, { "user1" }, RecordingTransport(), exec, now = { 42L })
        p.screen("Checkout")
        p.addAction("click", "Button#pay")
        repeat(6) { p.addAction("click", "x$it") }
        val b = p.body(leaving = true)
        assertTrue(b, b.startsWith("{\"key\":\"abw_1\",\"sessionId\":\"sid\",\"user\":\"user1\",\"release\":\"1.0\",\"path\":\"app://Checkout\",\"title\":\"\",\"actions\":["))
        assertTrue(b.contains("\"leaving\":true"))
        assertEquals(Presence.MAX_ACTIONS, Regex("\"type\":\"click\"").findAll(b).count())
        exec.shutdown()
    }
}
