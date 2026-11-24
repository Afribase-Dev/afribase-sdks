package com.afribase.watch

import android.app.Activity
import android.app.Application
import android.os.Looper
import android.os.SystemClock
import android.text.InputType
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.android.controller.ActivityController
import org.robolectric.annotation.Config
import java.time.Duration
import java.util.concurrent.CopyOnWriteArrayList

class RecordingTransport(@Volatile var code: Int = 202) : Transport {
    val posts = CopyOnWriteArrayList<Pair<String, String>>()
    override fun post(url: String, body: ByteArray, key: String): Int {
        posts.add(url to String(body, Charsets.UTF_8))
        return code
    }
}

class FormActivity : Activity() {
    lateinit var dead: Button
    lateinit var email: EditText
    lateinit var password: EditText

    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        dead = Button(this).apply { text = "Nothing"; id = View.generateViewId(); setOnClickListener { } }
        email = EditText(this).apply { hint = "Email"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS }
        password = EditText(this).apply { hint = "Password"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        root.addView(dead)
        root.addView(email)
        root.addView(password)
        setContentView(root)
    }
}

/** The Android glue end to end: real taps, typing and lifecycle through Robolectric. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WatchAndroidUxTest {
    private val app: Application = ApplicationProvider.getApplicationContext()
    private val transport = RecordingTransport()
    private var client: WatchClient? = null

    @After
    fun tearDown() {
        client?.stop()
    }

    private fun start(config: WatchConfig = WatchConfig("abw_test", "https://api.test/watch/ingest", live = false)): WatchClient =
        WatchClient(app, config, transport).also { it.start(); client = it }

    private fun idle(ms: Long = 0) {
        if (ms > 0) shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(ms)) else shadowOf(Looper.getMainLooper()).idle()
    }

    private fun tap(a: Activity, v: View) {
        val loc = IntArray(2)
        v.getLocationOnScreen(loc)
        val x = loc[0] + v.width / 2f
        val y = loc[1] + v.height / 2f
        val t = SystemClock.uptimeMillis()
        a.window.callback.dispatchTouchEvent(MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, x, y, 0))
        a.window.callback.dispatchTouchEvent(MotionEvent.obtain(t, t + 10, MotionEvent.ACTION_UP, x, y, 0))
        idle()
    }

    /** Every event sent so far. */
    private fun events(): List<String> {
        client!!.flush()
        val end = System.currentTimeMillis() + 3000
        var last = -1
        while (System.currentTimeMillis() < end) {
            Thread.sleep(50)
            if (transport.posts.size == last) break
            last = transport.posts.size
        }
        return transport.posts.filter { it.first.contains("/watch/ingest?") }.map { it.second }
    }

    private fun ux(type: String) = events().joinToString("\n").split("{\"kind\":").count { it.startsWith("\"ux\"") && it.contains("\"type\":\"$type\"") }

    private fun launch(): Pair<ActivityController<FormActivity>, FormActivity> {
        val c = Robolectric.buildActivity(FormActivity::class.java).setup().visible()
        idle()
        return c to c.get()
    }

    @Test
    fun rageAndDeadTapsFromRealTouches() {
        start()
        val (_, a) = launch()
        repeat(4) { tap(a, a.dead) }
        idle(1500)
        assertEquals(1, ux("rage_click"))
        assertEquals(0, ux("dead_click"))
        idle(6000)
        tap(a, a.dead)
        idle(1500)
        assertEquals(1, ux("dead_click"))
        val all = events().joinToString()
        assertTrue(all, all.contains("\"element\":{\"tag\":\"Button\",\"kind\":\"button\""))
    }

    @Test
    fun formAbandonOnBackgroundWithLastFieldAndNoValues() {
        start()
        val (controller, a) = launch()
        a.email.requestFocus()
        idle()
        a.email.setText("S3NT1NEL-typed@example.com")
        a.password.requestFocus()
        idle()
        a.password.setText("S3NT1NEL-pass")
        controller.pause().stop()
        idle()
        val all = events().joinToString("\n")
        assertEquals(1, ux("form_abandon"))
        assertTrue(all, all.contains("\"form\":\"FormActivity\",\"field\":\"Password\",\"fieldType\":\"password\""))
        assertFalse(all.contains("S3NT1NEL"))
    }

    @Test
    fun uxOffSendsNoSignals() {
        start(WatchConfig("abw_test", "https://api.test/watch/ingest", live = false, ux = false))
        val (controller, a) = launch()
        repeat(5) { tap(a, a.dead) }
        idle(2000)
        a.email.requestFocus()
        a.email.setText("x")
        controller.pause().stop()
        idle()
        assertFalse(events().joinToString().contains("\"kind\":\"ux\""))
    }

    @Test
    fun neverSendsTypedText() {
        val sentinel = "S3NT1NEL-typed-4242"
        start(WatchConfig("abw_test", "https://api.test/watch/ingest", live = true, replay = true, maskAllText = false))
        val (controller, a) = launch()
        a.email.requestFocus()
        a.email.setText("$sentinel-email")
        a.password.requestFocus()
        a.password.setText("$sentinel-pw")
        repeat(4) { tap(a, a.email) }
        repeat(4) { tap(a, a.password) }
        tap(a, a.dead)
        client!!.captureError(IllegalStateException("boom"), null)
        client!!.log("note", mapOf("screen" to "FormActivity"))
        idle(1500)
        controller.pause().stop()
        idle()
        val all = events().joinToString("\n") + transport.posts.joinToString("\n") { it.second }
        assertTrue(all.contains("\"kind\":\"log\""))
        assertTrue(all.contains("\"kind\":\"error\""))
        assertTrue(all.contains("\"leaving\":true"))
        assertFalse(all.contains("S3NT1NEL"))
    }
}
