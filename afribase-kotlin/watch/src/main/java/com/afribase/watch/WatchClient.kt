package com.afribase.watch

import android.app.Activity
import android.app.Application
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.Log
import android.view.Choreographer
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewTreeObserver
import android.widget.CompoundButton
import android.widget.EditText
import com.afribase.watch.compose.ComposeSupport
import com.afribase.watch.replay.ReplayMeta
import com.afribase.watch.replay.WireframeRecorder
import java.io.File
import java.lang.ref.WeakReference
import java.security.SecureRandom
import java.util.WeakHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/**
 * The running SDK (watch.ts on Android). All network and disk work happens
 * on one background worker thread; the main thread only records cheap facts,
 * so Watch never causes an ANR. Nothing here throws into the host app.
 */
internal class WatchClient(
    context: Context,
    private val config: WatchConfig,
    private val transport: Transport = HttpTransport(),
) : Application.ActivityLifecycleCallbacks {
    private val app = context.applicationContext as Application
    private val main = Handler(Looper.getMainLooper())
    private val worker: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor { r ->
        Thread(r, "afribase-watch").apply {
            isDaemon = true
            priority = Thread.MIN_PRIORITY + 1
        }
    }
    private val dir = File(app.filesDir, "afribase-watch")
    private val events = EventStore(File(dir, "events"), maxFiles = MAX_STORED, suffix = ".json")
    private val replays = EventStore(File(dir, "replays"), maxFiles = 3, suffix = ".json.gz")
    private val crumbs = Breadcrumbs()
    private val env = EventEnv(
        release = config.release,
        environment = config.environment,
        os = "Android " + Build.VERSION.RELEASE,
        model = (Build.MANUFACTURER + " " + Build.MODEL).trim(),
        sdkVersion = BuildConfig.SDK_VERSION,
    )
    private val ingestURL = Urls.ingest(config.endpoint, config.key)
    private val random = SecureRandom()
    private val sampleRate = config.sampleRate.coerceIn(0.0, 1.0)

    @Volatile var sessionId: String = newSessionId()
        private set
    @Volatile private var stopped = false
    @Volatile private var screen: String? = null
    private var started = 0
    private var backgroundAt = 0L
    private var current: WeakReference<Activity>? = null
    private val created = WeakHashMap<Activity, Long>()
    private val wrapped = WeakHashMap<Activity, Boolean>()
    private val manualScreens = WeakHashMap<Activity, String>()
    private val watchedFields = WeakHashMap<EditText, Boolean>()
    private var layoutListener: Pair<WeakReference<View>, ViewTreeObserver.OnGlobalLayoutListener>? = null
    private var focusListener: Pair<WeakReference<View>, ViewTreeObserver.OnGlobalFocusChangeListener>? = null
    private var previousHandler: Thread.UncaughtExceptionHandler? = null
    private var lastMove = 0L

    // Worker-thread state for retries.
    private var queued = 0
    private var backoffMs = 0L
    private var retryAt = 0L

    private val ux: UxTracker? = if (config.ux) {
        UxTracker(
            emit = { type, data -> uxEvent(type, data) },
            now = SystemClock::uptimeMillis,
            schedule = { delay, block -> main.postDelayed({ safe(block) }, delay) },
        )
    } else {
        null
    }

    private val presence: Presence? = if (config.live) {
        Presence(
            url = Urls.sub(config.endpoint, "presence", config.key),
            key = config.key,
            release = config.release,
            sessionId = { sessionId },
            user = ::user,
            transport = transport,
            worker = worker,
            title = { if (config.maskAllText) "" else Presence.maskTitle(current?.get()?.title?.toString() ?: "") },
        )
    } else {
        null
    }

    private val recorder: WireframeRecorder? = if (config.replay) {
        WireframeRecorder(
            url = Urls.sub(config.endpoint, "replay", config.key),
            key = config.key,
            maskAllText = config.maskAllText,
            maskAllInputs = config.maskAllInputs,
            replayOnSecureWindows = config.replayOnSecureWindows,
            meta = { trigger -> replayMeta(trigger) },
            transport = transport,
            worker = worker,
            pending = replays,
            log = ::debug,
            compose = ComposeSupport.bridge(),
        )
    } else {
        null
    }

    fun start() {
        installCrashHandler()
        app.registerActivityLifecycleCallbacks(this)
        worker.execute { queued = events.list().size }
        worker.scheduleWithFixedDelay({ flushNow() }, 0, FLUSH_MS, TimeUnit.MILLISECONDS)
        recorder?.let { r -> worker.execute { r.sendPending() } }
    }

    fun stop() {
        if (stopped) return
        try {
            ux?.beforeLeave()
        } catch (_: Throwable) {
        }
        presence?.stop()
        recorder?.stop()
        flush(force = true)
        stopped = true
        try {
            app.unregisterActivityLifecycleCallbacks(this)
        } catch (_: Throwable) {
        }
        detachListeners()
        val h = Thread.getDefaultUncaughtExceptionHandler()
        if (h is CrashHandler && h.owner === this) Thread.setDefaultUncaughtExceptionHandler(previousHandler)
        worker.shutdown()
    }

    // ── Errors ──────────────────────────────────────────────────────────

    /** captureError in the JS SDK. Sampled by sampleRate. */
    fun captureError(t: Throwable, context: Map<String, Any?>?) {
        if (stopped) return
        try {
            val msg = EventBuilder.message(t)
            onMain { ux?.error(msg) }
            if (sampleRate < 1.0 && random.nextDouble() >= sampleRate) return
            val ev = EventBuilder.error(
                t, fatal = false, thread = Thread.currentThread().name, env = env, sessionId = sessionId,
                userId = user(), screen = screen, crumbs = crumbs.snapshot(), context = context, now = System.currentTimeMillis(),
            )
            enqueue(Json.write(ev))
            recorder?.error(msg, null)
            recorder?.trigger("error")
        } catch (_: Throwable) {
        }
    }

    /** A `log` event: a message worth seeing in Watch that is not an exception. */
    fun log(message: String, context: Map<String, Any?>?) {
        push("log", message, context)
    }

    private inner class CrashHandler(val owner: WatchClient) : Thread.UncaughtExceptionHandler {
        override fun uncaughtException(thread: Thread, e: Throwable) {
            try {
                if (!stopped) {
                    val ev = EventBuilder.error(
                        e, fatal = true, thread = thread.name, env = env, sessionId = sessionId,
                        userId = user(), screen = screen, crumbs = crumbs.snapshot(), context = null, now = System.currentTimeMillis(),
                    )
                    // Synchronous: the process is about to die. Sent on the next launch.
                    events.save(Json.write(ev).toByteArray(Charsets.UTF_8))
                    recorder?.persistForCrash(EventBuilder.message(e))
                }
            } catch (_: Throwable) {
            } finally {
                val prev = previousHandler
                if (prev != null) {
                    prev.uncaughtException(thread, e)
                } else {
                    android.os.Process.killProcess(android.os.Process.myPid())
                    System.exit(10)
                }
            }
        }
    }

    private fun installCrashHandler() {
        previousHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler(CrashHandler(this))
    }

    // ── Events, queue, flushing ─────────────────────────────────────────

    private fun uxEvent(type: String, data: Map<String, Any?>) {
        val ctx = LinkedHashMap<String, Any?>()
        ctx["type"] = type
        ctx.putAll(data)
        push("ux", UxTracker.message(type, data), ctx)
    }

    /** A non-error event (`ux`, `slow`, `http`, `log`). Not sampled, as in JS. */
    fun push(kind: String, message: String, context: Map<String, Any?>?, extra: Map<String, Any?>? = null) {
        if (stopped) return
        try {
            val ev = EventBuilder.base(kind, message, env, sessionId, user(), screen, crumbs.snapshot(), context, System.currentTimeMillis())
            if (extra != null) ev.putAll(extra)
            enqueue(Json.write(ev))
            if (kind == "ux") recorder?.trigger("ux")
        } catch (_: Throwable) {
        }
    }

    fun breadcrumb(type: String, data: Map<String, Any?>) {
        if (!stopped) crumbs.add(type, data)
    }

    /** Persists on the worker; flushes once 20 are waiting (as JS does). */
    private fun enqueue(json: String) {
        debug("event: " + json.take(300))
        try {
            worker.execute {
                events.save(json.toByteArray(Charsets.UTF_8))
                if (++queued >= FLUSH_AT) flushNow(force = true)
            }
        } catch (_: Throwable) {
        }
    }

    fun flush(force: Boolean = true) {
        try {
            worker.execute { flushNow(force) }
        } catch (_: Throwable) {
        }
    }

    /**
     * Worker: sends stored events, at most 50 and 256 KB per request, oldest
     * first. On a network error, 5xx, 408 or 429 the events stay on disk and
     * the next try waits 5 s, 10 s, 20 s ... up to 5 min (an explicit flush
     * skips the wait).
     */
    private fun flushNow(force: Boolean = false) {
        try {
            if (!force && System.currentTimeMillis() < retryAt) return
            var rounds = 0
            while (rounds++ < 10) {
                val files = events.list()
                queued = files.size
                if (files.isEmpty()) return
                val bodies = ArrayList<String>(MAX_BATCH)
                val used = ArrayList<File>(MAX_BATCH)
                var size = 16
                for (f in files) {
                    if (bodies.size >= MAX_BATCH) break
                    val b = events.read(f)
                    if (b == null || b.size > MAX_BODY) {
                        events.delete(f)
                        continue
                    }
                    if (size + b.size + 1 > MAX_BODY) break
                    size += b.size + 1
                    bodies.add(String(b, Charsets.UTF_8))
                    used.add(f)
                }
                if (bodies.isEmpty()) return
                val code = transport.post(ingestURL, EventBuilder.batch(bodies).toByteArray(Charsets.UTF_8), config.key)
                debug("ingest ${bodies.size} events -> $code")
                if (!deliveredOrRejected(code)) {
                    backoffMs = if (backoffMs == 0L) FLUSH_MS else minOf(backoffMs * 2, MAX_BACKOFF_MS)
                    retryAt = System.currentTimeMillis() + backoffMs
                    return
                }
                backoffMs = 0L
                retryAt = 0L
                used.forEach { events.delete(it) }
                queued = maxOf(0, queued - used.size)
            }
        } catch (_: Throwable) {
        }
    }

    // ── HTTP (from WatchInterceptor) ────────────────────────────────────

    /** A request finished (status 0 = network error). Mirrors the JS fetch wrapper. */
    fun noteRequest(method: String, url: String, status: Int, ms: Long, failure: String?) {
        if (stopped) return
        onMain { ux?.request() }
        breadcrumb("fetch", mapOf("method" to method, "url" to url, "status" to status, "ms" to ms))
        val extra = mapOf("url" to url, "method" to method, "status" to status, "durationMs" to ms)
        when {
            failure != null -> push("http", "$method $url failed: $failure", null, extra)
            status >= 500 -> push("http", "$method $url -> $status", null, extra)
            ms > SLOW_REQUEST_MS -> push("slow", "Slow request: $method $url $ms ms", null, extra)
        }
    }

    // ── Screens, touches, lifecycle ─────────────────────────────────────

    fun setScreen(name: String) {
        onMain {
            val n = name.take(100)
            current?.get()?.let { manualScreens[it] = n }
            changeScreen(n, "setScreen")
        }
    }

    private fun changeScreen(name: String, how: String) {
        if (name == screen) return
        screen = name
        crumbs.add("navigation", mapOf("how" to how, "to" to EventBuilder.screenUrl(name)))
        ux?.navigation(name)
        presence?.screen(name)
        recorder?.setScreen(name)
    }

    private fun onTouch(activity: Activity, ev: MotionEvent) {
        val r = recorder
        val density = activity.resources.displayMetrics.density
        val x = ev.rawX / density
        val y = ev.rawY / density
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> r?.touch("down", x, y)
            MotionEvent.ACTION_MOVE -> {
                val now = SystemClock.uptimeMillis()
                if (r != null && now - lastMove >= MOVE_THROTTLE_MS) {
                    lastMove = now
                    r.touch("move", x, y)
                }
            }
            MotionEvent.ACTION_UP -> {
                r?.touch("up", x, y)
                val decor = activity.window?.peekDecorView()
                val view = if (decor != null) ViewFinder.at(decor, ev.rawX, ev.rawY) else null
                val d = ViewFinder.describe(view, config.maskAllText)
                if (d != null) crumbs.add("click", d)
                presence?.addAction("click", ViewFinder.label(d))
                val tracker = ux ?: return
                tracker.tap(d, tappable(view), screen)
                measureInteraction(d, "tap")
            }
        }
    }

    private fun onKey(ev: KeyEvent) {
        if (ev.action != KeyEvent.ACTION_UP || ux == null) return
        val focused = current?.get()?.currentFocus
        measureInteraction(ViewFinder.describe(focused, config.maskAllText), "key")
    }

    /** Looks like it should react to a tap: a clickable view that is not a field or a toggle. */
    private fun tappable(v: View?): Boolean {
        if (v == null || !v.isClickable || !v.isEnabled) return false
        if (v is EditText || v is CompoundButton) return false
        return true
    }

    /** slow_interaction: the input, its handlers (posted clicks included), then the next frame. */
    private fun measureInteraction(element: Map<String, Any?>?, type: String) {
        val tracker = ux ?: return
        val start = SystemClock.uptimeMillis()
        main.post {
            try {
                Choreographer.getInstance().postFrameCallback {
                    safe { tracker.interaction(element, type, SystemClock.uptimeMillis() - start) }
                }
            } catch (_: Throwable) {
            }
        }
    }

    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
        created[activity] = SystemClock.uptimeMillis()
        wrapWindow(activity)
    }

    override fun onActivityStarted(activity: Activity) {
        if (started++ == 0) {
            val now = SystemClock.elapsedRealtime()
            if (backgroundAt != 0L && now - backgroundAt > SESSION_IDLE_MS) {
                sessionId = newSessionId()
                recorder?.newSession()
            }
            // Name the screen before the first heartbeat.
            changeScreen(manualScreens[activity] ?: screenName(activity), "activity")
            presence?.foreground()
            recorder?.foreground()
            crumbs.add("lifecycle", mapOf("state" to "foreground"))
        }
    }

    override fun onActivityResumed(activity: Activity) {
        wrapWindow(activity)
        current = WeakReference(activity)
        val name = manualScreens[activity] ?: screenName(activity)
        recorder?.setActivity(activity, name)
        changeScreen(name, "activity")
        attachListeners(activity)
        measureFirstFrame(activity, name)
    }

    override fun onActivityPaused(activity: Activity) {
        detachListeners()
    }

    override fun onActivityStopped(activity: Activity) {
        if (started > 0 && --started == 0) {
            backgroundAt = SystemClock.elapsedRealtime()
            ux?.beforeLeave()
            crumbs.add("lifecycle", mapOf("state" to "background"))
            presence?.background()
            recorder?.background()
            recorder?.setActivity(null, null)
            flush(force = true)
        }
    }

    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}

    override fun onActivityDestroyed(activity: Activity) {
        created.remove(activity)
        wrapped.remove(activity)
        manualScreens.remove(activity)
        if (current?.get() === activity) current = null
    }

    private fun wrapWindow(activity: Activity) {
        if (wrapped[activity] == true) return
        val window = activity.window ?: return
        val cb = window.callback ?: return
        if (cb is WatchWindowCallback) {
            wrapped[activity] = true
            return
        }
        window.callback = WatchWindowCallback(cb, onTouch = { ev -> if (!stopped) onTouch(activity, ev) }, onKey = { ev -> if (!stopped) onKey(ev) })
        wrapped[activity] = true
    }

    /** Layout changes count as "something reacted" (dead taps); typing marks forms. */
    private fun attachListeners(activity: Activity) {
        detachListeners()
        val tracker = ux ?: return
        val decor = activity.window?.peekDecorView() ?: return
        val vto = decor.viewTreeObserver
        if (!vto.isAlive) return
        val layout = ViewTreeObserver.OnGlobalLayoutListener { tracker.activity() }
        val focus = ViewTreeObserver.OnGlobalFocusChangeListener { _, now -> if (now is EditText) watchField(now) }
        vto.addOnGlobalLayoutListener(layout)
        vto.addOnGlobalFocusChangeListener(focus)
        layoutListener = WeakReference(decor) to layout
        focusListener = WeakReference(decor) to focus
        activity.currentFocus?.let { if (it is EditText) watchField(it) }
    }

    private fun detachListeners() {
        layoutListener?.let { (v, l) ->
            try {
                v.get()?.viewTreeObserver?.takeIf { it.isAlive }?.removeOnGlobalLayoutListener(l)
            } catch (_: Throwable) {
            }
        }
        focusListener?.let { (v, l) ->
            try {
                v.get()?.viewTreeObserver?.takeIf { it.isAlive }?.removeOnGlobalFocusChangeListener(l)
            } catch (_: Throwable) {
            }
        }
        layoutListener = null
        focusListener = null
    }

    /**
     * Watches a field the user focused: typing while it has focus marks the
     * screen's form as touched, with this field as the last one. The text
     * itself is never read.
     */
    private fun watchField(field: EditText) {
        if (watchedFields[field] == true) return
        watchedFields[field] = true
        field.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                if (stopped || !field.hasFocus()) return
                safe { ux?.field(screen ?: "unknown", fieldIdentity(field), fieldType(field)) }
            }
        })
    }

    /** One `slow` event when the first frame of a new screen comes after slowScreenMs. */
    private fun measureFirstFrame(activity: Activity, name: String) {
        if (!config.ux) return
        val start = created.remove(activity) ?: return
        val decor = activity.window?.peekDecorView() ?: return
        val vto = decor.viewTreeObserver
        if (!vto.isAlive) return
        val listener = object : ViewTreeObserver.OnDrawListener {
            var done = false
            override fun onDraw() {
                if (done) return
                done = true
                val ms = SystemClock.uptimeMillis() - start
                decor.post {
                    try {
                        decor.viewTreeObserver.removeOnDrawListener(this)
                    } catch (_: Throwable) {
                    }
                }
                crumbs.add("screen_load", mapOf("screen" to name, "ms" to ms))
                if (ms > config.slowScreenMs) {
                    push("slow", "Slow screen load: $ms ms", mapOf("screen" to name), mapOf("durationMs" to ms))
                }
            }
        }
        vto.addOnDrawListener(listener)
    }

    private fun screenName(a: Activity): String = a.javaClass.simpleName.ifEmpty { a.javaClass.name }.take(100)

    // ── Helpers ─────────────────────────────────────────────────────────

    private fun replayMeta(trigger: String): ReplayMeta {
        val dm = app.resources.displayMetrics
        val decor = current?.get()?.window?.peekDecorView()
        val wPx = decor?.width?.takeIf { it > 0 } ?: dm.widthPixels
        val hPx = decor?.height?.takeIf { it > 0 } ?: dm.heightPixels
        return ReplayMeta(
            key = config.key,
            sessionId = sessionId,
            user = user(),
            release = config.release,
            environment = config.environment,
            screen = screen ?: "unknown",
            device = linkedMapOf(
                "os" to env.os,
                "model" to env.model,
                "w" to Math.round(wPx / dm.density),
                "h" to Math.round(hPx / dm.density),
                "density" to dm.density,
            ),
            trigger = trigger,
        )
    }

    private fun user(): String? = try {
        config.user?.invoke()
    } catch (_: Throwable) {
        null
    }

    private fun newSessionId(): String {
        val b = ByteArray(8)
        random.nextBytes(b)
        return b.joinToString("") { "%02x".format(it) } + java.lang.Long.toString(System.currentTimeMillis(), 36)
    }

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) safe(block) else main.post { safe(block) }
    }

    private fun safe(block: () -> Unit) {
        try {
            block()
        } catch (_: Throwable) {
        }
    }

    private fun debug(msg: String) {
        if (config.debug) Log.d(TAG, msg)
    }

    companion object {
        const val TAG = "AfribaseWatch"
        const val FLUSH_MS = 5_000L
        const val FLUSH_AT = 20
        const val MAX_BATCH = 50
        const val MAX_BODY = 256 * 1024
        const val MAX_STORED = 200
        const val MAX_BACKOFF_MS = 5 * 60_000L
        const val MOVE_THROTTLE_MS = 100L
        const val SESSION_IDLE_MS = 30 * 60_000L
        const val SLOW_REQUEST_MS = 4_000L

        /** Field identity: resource id name, else its hint, else the class. Never its value. */
        fun fieldIdentity(f: EditText): String {
            if (f.id != View.NO_ID) {
                try {
                    return f.resources.getResourceEntryName(f.id).take(60)
                } catch (_: Exception) {
                }
            }
            f.hint?.toString()?.trim()?.takeIf { it.isNotEmpty() }?.let { return it.take(60) }
            return f.javaClass.simpleName.ifEmpty { "EditText" }
        }

        /** `text`, `email`, `password`, `number`, `phone`, `multiline` ... like an input's type. */
        fun fieldType(f: EditText): String {
            val t = f.inputType
            val cls = t and InputType.TYPE_MASK_CLASS
            val v = t and InputType.TYPE_MASK_VARIATION
            if (com.afribase.watch.replay.ViewWalker.isSecret(f)) return "password"
            return when (cls) {
                InputType.TYPE_CLASS_NUMBER -> "number"
                InputType.TYPE_CLASS_PHONE -> "tel"
                InputType.TYPE_CLASS_DATETIME -> "date"
                InputType.TYPE_CLASS_TEXT -> when {
                    v == InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS || v == InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS -> "email"
                    v == InputType.TYPE_TEXT_VARIATION_URI -> "url"
                    t and InputType.TYPE_TEXT_FLAG_MULTI_LINE != 0 -> "textarea"
                    else -> "text"
                }
                else -> "text"
            }
        }
    }
}

