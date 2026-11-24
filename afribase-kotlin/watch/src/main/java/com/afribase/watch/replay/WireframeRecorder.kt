package com.afribase.watch.replay

import android.app.Activity
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.WindowInsets
import com.afribase.watch.EventStore
import com.afribase.watch.Gzip
import com.afribase.watch.Json
import com.afribase.watch.Transport
import com.afribase.watch.deliveredOrRejected
import java.lang.ref.WeakReference
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/**
 * Wireframe session replay (watch-wireframe-contract.md). Walks the current
 * Activity's View tree at most every 500 ms on the main thread (skipping
 * ticks after a walk over the 4 ms budget), turns changed trees into
 * `snapshot` events (or a keyframe every 10 s), and keeps the last 60 s.
 * Serialising and gzip run on the worker thread. Never takes pixels.
 */
internal class WireframeRecorder(
    private val url: String,
    private val key: String,
    private val maskAllText: Boolean,
    private val meta: (trigger: String) -> ReplayMeta,
    private val transport: Transport,
    private val worker: ScheduledExecutorService,
    private val pending: EventStore,
    private val log: (String) -> Unit,
    private val compose: ComposeBridge? = null,
    private val replayOnSecureWindows: Boolean = false,
) {
    private val main = Handler(Looper.getMainLooper())
    val buffer = ReplayBuffer()
    val gate = UploadGate()
    private val policy = SnapshotPolicy()
    private val walker = ViewWalker(compose)
    private val ids = NodeIds()
    private val origin = IntArray(2)

    private var activity: WeakReference<Activity>? = null
    private var screen: String = "unknown"
    @Volatile var secure = false
        private set
    private var running = false
    @Volatile private var stopped = false
    private var skip = 0
    private var lastScrolls: Map<Int, Long> = emptyMap()
    private var keyboard: Pair<Boolean, Int>? = null

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            try {
                walkOnce()
            } catch (t: Throwable) {
                log("walk failed: $t")
            }
            main.postDelayed(this, INTERVAL_MS)
        }
    }

    /** Main thread: the visible Activity changed (null when none). */
    fun setActivity(a: Activity?, name: String?) {
        activity = a?.let { WeakReference(it) }
        if (a != null && name != null && name != screen) {
            screen = name
            secure = treatAsSecure(a)
            lastScrolls = emptyMap()
            add("screen", mapOf("screen" to name, "secure" to secure))
            policy.reset()
        }
    }

    /** Main thread: a manual screen name (single-Activity apps). */
    fun setScreen(name: String) {
        if (name == screen) return
        screen = name
        add("screen", mapOf("screen" to name, "secure" to secure))
        policy.reset()
    }

    fun foreground() {
        add("lifecycle", mapOf("state" to "foreground"))
        if (!running && !stopped) {
            running = true
            main.post(tick)
        }
    }

    fun background() {
        add("lifecycle", mapOf("state" to "background"))
        running = false
        main.removeCallbacks(tick)
    }

    /** Main thread. x/y in dp on screen; dropped on secure screens. */
    fun touch(phase: String, x: Float, y: Float) {
        val sec = secure || activity?.get()?.let { treatAsSecure(it) } == true
        if (sec) add("touch", mapOf("phase" to phase)) else add("touch", mapOf("phase" to phase, "x" to x, "y" to y))
    }

    /** An error was captured: a marker in the timeline (not on secure screens). */
    fun error(message: String, eventId: String?) {
        if (secure) return
        add("error", mapOf("message" to Masking.mask(message), "eventId" to eventId))
    }

    /** Watch sent an `error` or `ux` event: upload 5 s later, within the limits. */
    fun trigger(kind: String) {
        if (stopped) return
        if (!gate.tryTrigger(System.currentTimeMillis())) return
        worker.schedule({
            try {
                upload(kind)
            } finally {
                gate.done()
            }
        }, UploadGate.DELAY_MS, TimeUnit.MILLISECONDS)
    }

    /** The process is dying: write what we have so the next launch uploads it. Any thread. */
    fun persistForCrash(message: String) {
        if (stopped) return
        if (!gate.tryTrigger(System.currentTimeMillis())) return
        try {
            val t = System.currentTimeMillis()
            if (!secure) {
                buffer.add(BufferedEvent(t, "error", Json.write(linkedMapOf("t" to t, "type" to "error", "message" to Masking.mask(message)))))
            }
            val events = buffer.events(t)
            if (events.isEmpty()) return
            val body = encode(meta("error"), events) ?: return
            pending.save(body)
        } catch (_: Throwable) {
        }
    }

    /** Worker: uploads replays saved by a crash on an earlier launch. */
    fun sendPending() {
        for (f in pending.list()) {
            val bytes = pending.read(f) ?: continue
            val code = transport.post(url, bytes, key)
            if (deliveredOrRejected(code)) pending.delete(f) else return
        }
    }

    /** A new session: forget the old one's replay. */
    fun newSession() {
        buffer.clear()
        gate.newSession()
        policy.reset()
    }

    fun stop() {
        stopped = true
        running = false
        main.removeCallbacks(tick)
        buffer.clear()
    }

    private fun upload(trigger: String) {
        if (stopped) return
        val events = buffer.events(System.currentTimeMillis())
        if (events.isEmpty()) return
        val body = encode(meta(trigger), events) ?: return
        val code = transport.post(url, body, key)
        log("replay upload ($trigger, ${events.size} events, ${body.size} B) -> $code")
    }

    private fun encode(m: ReplayMeta, all: List<BufferedEvent>): ByteArray? {
        var events = all
        repeat(4) {
            val body = Gzip.encode(ReplayPayload.build(m, events))
            if (body.size <= UploadGate.MAX_BODY_BYTES) return body
            events = ReplayPayload.halve(events) ?: return null
        }
        return null
    }

    /** Main thread: one walk, maybe one snapshot. */
    internal fun walkOnce() {
        if (skip > 0) {
            skip--
            return
        }
        val a = activity?.get() ?: return
        if (a.isFinishing) return
        val window = a.window ?: return
        val decor = window.peekDecorView() ?: return
        if (decor.width <= 0 || decor.height <= 0) return
        val started = System.nanoTime()
        decor.getLocationOnScreen(origin)
        val dm = a.resources.displayMetrics
        val flagSecure = (window.attributes.flags and android.view.WindowManager.LayoutParams.FLAG_SECURE) != 0
        val ctx = WalkContext(
            density = dm.density,
            screenWpx = decor.width + maxOf(0, origin[0]),
            screenHpx = decor.height + maxOf(0, origin[1]),
            // A FLAG_SECURE window recorded on the owner's say-so: text is
            // always masked there, whatever maskAllText says.
            maskAllText = maskAllText || (replayOnSecureWindows && flagSecure),
            ids = ids,
            deadlineNanos = started + HARD_CAP_NANOS,
        )
        val flags = if (replayOnSecureWindows) window.attributes.flags and android.view.WindowManager.LayoutParams.FLAG_SECURE.inv() else window.attributes.flags
        val result = walker.walk(screen, decor, flags, origin, ctx)
        val elapsed = System.nanoTime() - started
        if (elapsed > BUDGET_NANOS) {
            // Over budget: skip the next tick(s), more for slower walks.
            skip = minOf(4, (elapsed / BUDGET_NANOS).toInt())
        }
        if (result.secure != secure) {
            secure = result.secure
            add("screen", mapOf("screen" to screen, "secure" to secure))
        }
        val t = System.currentTimeMillis()
        if (!result.secure) {
            scrollEvents(ctx.scrolls, t)
            keyboardEvent(decor, dm.density, t)
        } else {
            lastScrolls = emptyMap()
        }
        if (policy.shouldEmit(result.hash, screen, t)) {
            worker.execute {
                try {
                    buffer.add(BufferedEvent(t, ReplayBuffer.TYPE_SNAPSHOT, snapshotJson(t, result)))
                } catch (_: Throwable) {
                }
            }
        }
    }

    private fun scrollEvents(now: Map<Int, Long>, t: Long) {
        for ((id, v) in now) {
            val prev = lastScrolls[id] ?: continue
            if (prev == v) continue
            val dx = (v shr 32).toInt() - (prev shr 32).toInt()
            val dy = v.toInt() - prev.toInt()
            add("scroll", mapOf("id" to id, "dx" to dx, "dy" to dy), t)
        }
        lastScrolls = HashMap(now)
    }

    private fun keyboardEvent(decor: android.view.View, density: Float, t: Long) {
        if (Build.VERSION.SDK_INT < 30) return
        val insets = decor.rootWindowInsets ?: return
        val visible = insets.isVisible(WindowInsets.Type.ime())
        val h = Math.round(insets.getInsets(WindowInsets.Type.ime()).bottom / density)
        val state = visible to h
        if (state == keyboard) return
        val first = keyboard == null
        keyboard = state
        if (first && !visible) return
        add("keyboard", mapOf("visible" to visible, "h" to h), t)
    }

    /** Adds a small event (rendered right here; it is tiny). */
    private fun add(type: String, fields: Map<String, Any?>, t: Long = System.currentTimeMillis()) {
        if (stopped) return
        val m = LinkedHashMap<String, Any?>(fields.size + 2)
        m["t"] = t
        m["type"] = type
        m.putAll(fields)
        val json = Json.write(m)
        worker.execute { buffer.add(BufferedEvent(t, type, json)) }
    }

    /** FLAG_SECURE counts as a secure screen unless the owner opted in. */
    private fun treatAsSecure(a: Activity): Boolean = !replayOnSecureWindows && isWindowSecure(a)

    companion object {
        const val INTERVAL_MS = 500L
        const val BUDGET_NANOS = 4_000_000L
        const val HARD_CAP_NANOS = 16_000_000L

        fun isWindowSecure(a: Activity): Boolean = try {
            (a.window.attributes.flags and android.view.WindowManager.LayoutParams.FLAG_SECURE) != 0
        } catch (_: Throwable) {
            false
        }

        /** The `snapshot` event (watch-wireframe-contract.md). */
        fun snapshotJson(t: Long, r: WalkResult): String {
            val sb = StringBuilder(if (r.root == null) 128 else 64 + r.nodes * 80)
            sb.append("{\"t\":").append(t)
            sb.append(",\"type\":\"snapshot\",\"screen\":")
            Json.string(sb, r.screen)
            sb.append(",\"w\":"); Json.number(sb, r.w.toDouble())
            sb.append(",\"h\":"); Json.number(sb, r.h.toDouble())
            sb.append(",\"secure\":").append(r.secure)
            if (r.truncated) sb.append(",\"truncated\":true")
            sb.append(",\"root\":")
            if (r.root == null) sb.append("null") else r.root.render(sb)
            sb.append('}')
            return sb.toString()
        }
    }
}
