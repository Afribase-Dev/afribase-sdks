package com.afribase.watch.replay

import android.app.Activity
import android.os.Looper
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import com.afribase.watch.EventStore
import com.afribase.watch.Transport
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPInputStream

/** Real Activity -> walk -> buffer -> gzip body, as an upload would send it. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WireframeRecorderTest {
    @get:Rule val tmp = TemporaryFolder()

    private val worker = Executors.newSingleThreadScheduledExecutor()
    private val noTransport = object : Transport {
        override fun post(url: String, body: ByteArray, key: String) = 202
    }

    private fun recorder(store: EventStore, maskAllText: Boolean = true, replayOnSecureWindows: Boolean = false) = WireframeRecorder(
        url = "https://api.test/watch/ingest/replay?key=k",
        key = "k",
        maskAllText = maskAllText,
        replayOnSecureWindows = replayOnSecureWindows,
        meta = { trigger ->
            ReplayMeta("k", "sid", null, "1.0", "test", "MainActivity", linkedMapOf("os" to "Android 14", "w" to 320, "h" to 470, "density" to 1f), trigger)
        },
        transport = noTransport,
        worker = worker,
        pending = store,
        log = {},
    )

    private fun drain() {
        worker.submit {}.get(5, TimeUnit.SECONDS)
    }

    private fun body(store: EventStore): String {
        val f = store.list().single()
        val bytes = store.read(f)!!
        assertEquals(0x1f, bytes[0].toInt() and 0xff)
        assertEquals(0x8b, bytes[1].toInt() and 0xff)
        return GZIPInputStream(bytes.inputStream()).readBytes().toString(Charsets.UTF_8)
    }

    @Test
    fun recordsAWireframeAndWritesAGzipBody() {
        val a = Robolectric.buildActivity(Activity::class.java).setup().visible().get()
        a.setContentView(LinearLayout(a).apply { addView(TextView(a).apply { text = "Balance 1,000" }) })
        shadowOf(Looper.getMainLooper()).idle()

        val store = EventStore(tmp.newFolder("r"), 3, ".json.gz")
        val r = recorder(store)
        r.setActivity(a, "MainActivity")
        r.walkOnce()
        r.touch("down", 10f, 20f)
        r.walkOnce() // unchanged tree: no second snapshot
        drain()
        r.persistForCrash("java.lang.RuntimeException: boom")

        val json = body(store)
        assertTrue(json, json.contains("\"format\":\"wireframe\""))
        assertTrue(json.contains("\"platform\":\"android\""))
        assertTrue(json.contains("\"url\":\"app://MainActivity\""))
        assertTrue(json.contains("\"trigger\":\"error\""))
        assertEquals(1, Regex("\"type\":\"snapshot\"").findAll(json).count())
        assertTrue(json.contains("\"type\":\"touch\",\"phase\":\"down\",\"x\":10,\"y\":20"))
        assertTrue(json.contains("\"type\":\"error\",\"message\":\"********************************\""))
        assertTrue(json.contains("\"k\":\"text\""))
        assertTrue(json.contains("\"text\":\"*************\""))
        assertFalse(json.contains("Balance"))
        assertFalse(json.contains("boom"))
        // The events start at a snapshot.
        val firstType = Regex("\"events\":\\[\\{\"t\":\\d+,\"type\":\"(\\w+)\"").find(json)!!.groupValues[1]
        assertEquals("snapshot", firstType)
    }

    @Test
    fun secureWindowDropsTreeAndTouchCoordinates() {
        val a = Robolectric.buildActivity(Activity::class.java).setup().visible().get()
        a.setContentView(TextView(a).apply { text = "Secret" })
        a.window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        shadowOf(Looper.getMainLooper()).idle()

        val store = EventStore(tmp.newFolder("s"), 3, ".json.gz")
        val r = recorder(store)
        r.setActivity(a, "PinActivity")
        r.walkOnce()
        r.touch("down", 10f, 20f)
        drain()
        r.persistForCrash("boom")

        val json = body(store)
        assertTrue(json, json.contains("\"type\":\"snapshot\",\"screen\":\"PinActivity\""))
        assertTrue(json.contains("\"secure\":true,\"root\":null"))
        assertTrue(json.contains("\"type\":\"touch\",\"phase\":\"down\"}"))
        assertFalse(json.contains("\"x\":10"))
        assertFalse(json.contains("Secret"))
        // No error marker on a secure screen.
        assertFalse(json.contains("\"type\":\"error\""))
    }

    @Test
    fun secureWindowRecordedWhenOwnerOptsIn_textStillMasked() {
        val a = Robolectric.buildActivity(Activity::class.java).setup().visible().get()
        a.setContentView(TextView(a).apply { text = "Secret" })
        a.window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        shadowOf(Looper.getMainLooper()).idle()

        val store = EventStore(tmp.newFolder("o"), 3, ".json.gz")
        // maskAllText off on purpose: a FLAG_SECURE window still masks text.
        val r = recorder(store, maskAllText = false, replayOnSecureWindows = true)
        r.setActivity(a, "ChatActivity")
        r.walkOnce()
        r.touch("down", 10f, 20f)
        drain()
        r.persistForCrash("boom")

        val json = body(store)
        assertTrue(json, json.contains("\"type\":\"snapshot\",\"screen\":\"ChatActivity\""))
        assertTrue(json.contains("\"secure\":false"))
        assertFalse(json.contains("\"root\":null"))
        assertTrue(json.contains("\"text\":\"******\""))
        assertTrue(json.contains("\"x\":10"))
        assertFalse(json.contains("Secret"))
    }
}
