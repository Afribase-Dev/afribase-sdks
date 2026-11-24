package com.afribase.watch

/**
 * UX signals (watch-ux.ts on Android), from structure only:
 *
 *   rage_click          3+ taps on the same element within ~1 s (once per burst)
 *   dead_click          a tap on something that looks tappable, and within ~1 s
 *                       no layout change, navigation or request follows
 *   form_abandon        fields of a screen were typed into, then the screen or
 *                       the app was left without submitting; reports the form
 *                       and the LAST field touched (by id or hint), never values
 *   error_after_action  an error within ~2 s of a tap, with the element
 *   nav_loop            A -> B -> A -> B within 30 s
 *   slow_interaction    tap/key to next frame over ~500 ms
 *
 * At most 50 per app launch. Main thread only; the Android glue in
 * WatchClient feeds it. [schedule] runs a block later (Handler.postDelayed on
 * a device, a fake clock in tests).
 */
internal class UxTracker(
    private val emit: (type: String, data: Map<String, Any?>) -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
    private val schedule: (delayMs: Long, block: () -> Unit) -> Unit,
) {
    private class Burst {
        val times = ArrayList<Long>()
        var reported = false
    }

    private class LastTap(val at: Long, val element: Map<String, Any?>?, val form: String?) {
        var errored = false
    }

    private class FormState(val form: String, val field: String, val type: String, val at: Long)

    private var sent = 0
    private var lastActivity = 0L
    private val bursts = HashMap<String, Burst>()
    private val deadReported = HashMap<String, Long>()
    private var lastTap: LastTap? = null
    private val forms = LinkedHashMap<String, FormState>()
    private val trail = ArrayList<Pair<String, Long>>()
    private var lastPath: String? = null
    private val slowReported = HashMap<String, Long>()

    private fun send(type: String, data: Map<String, Any?>) {
        if (sent >= MAX_UX) return
        sent++
        emit(type, data)
    }

    /** Something visible reacted (layout change, request, navigation). */
    fun activity() {
        lastActivity = now()
    }

    /**
     * A tap. [element] describes the view; [tappable] when it looks like it
     * should do something (a dead-tap candidate); [form] the screen it is on.
     */
    fun tap(element: Map<String, Any?>?, tappable: Boolean, form: String?) {
        val t = now()
        val key = keyOf(element)
        lastTap = LastTap(t, element, form)

        var b = bursts[key]
        if (b == null) {
            if (bursts.size > 200) bursts.clear()
            b = Burst()
            bursts[key] = b
        }
        if (b.times.isNotEmpty() && t - b.times.last() > RAGE_WINDOW_MS) {
            b.times.clear()
            b.reported = false
        }
        b.times.add(t)
        b.times.removeAll { t - it > RAGE_WINDOW_MS }
        if (b.times.size >= RAGE_CLICKS && !b.reported) {
            b.reported = true
            send("rage_click", mapOf("element" to element, "clicks" to b.times.size))
        }

        if (tappable) {
            val burst = b
            schedule(DEAD_WINDOW_MS) {
                if (lastActivity >= t || burst.reported) return@schedule
                val last = deadReported[key] ?: 0L
                if (now() - last < DEAD_DEDUPE_MS) return@schedule
                deadReported[key] = now()
                send("dead_click", mapOf("element" to element))
            }
        }
    }

    /** The user typed into a field (identity only: never the value). */
    fun field(form: String, field: String, type: String) {
        forms[form] = FormState(form, field.take(60), type, now())
    }

    /** A form was submitted (IME send/done/go, or a submit tap followed by a request). */
    fun submitted(form: String) {
        forms.remove(form)
    }

    /** The app made a request: activity, and likely the submission of a form just tapped. */
    fun request() {
        activity()
        val c = lastTap
        if (c?.form != null && now() - c.at <= FORM_SENT_MS) forms.remove(c.form)
    }

    /** The screen changed. Leaving a screen abandons its forms. */
    fun navigation(path: String) {
        activity()
        if (path == lastPath) return
        reportAbandoned()
        lastPath = path
        val t = now()
        trail.add(path to t)
        if (trail.size > 6) trail.removeAt(0)
        val n = trail.size
        if (n >= 4) {
            val (a, at) = trail[n - 4]
            val (b, _) = trail[n - 3]
            val (c, _) = trail[n - 2]
            val (d, dt) = trail[n - 1]
            if (a == c && b == d && a != b && dt - at <= LOOP_WINDOW_MS) {
                send("nav_loop", mapOf("paths" to listOf(a, b)))
                trail.clear()
            }
        }
    }

    fun error(message: String) {
        val c = lastTap ?: return
        if (c.errored || now() - c.at > ERROR_WINDOW_MS) return
        c.errored = true
        send("error_after_action", mapOf("element" to c.element, "message" to message.take(200)))
    }

    /** Input to the next frame took [durationMs]. */
    fun interaction(element: Map<String, Any?>?, eventType: String, durationMs: Long) {
        if (durationMs < SLOW_MS) return
        val key = keyOf(element) + eventType
        val last = slowReported[key] ?: 0L
        if (last != 0L && now() - last < SLOW_DEDUPE_MS) return
        slowReported[key] = now()
        send("slow_interaction", mapOf("element" to element, "eventType" to eventType.take(30), "durationMs" to durationMs))
    }

    /** The app is going to the background: report abandoned forms. */
    fun beforeLeave() = reportAbandoned()

    private fun reportAbandoned() {
        for (st in forms.values) send("form_abandon", mapOf("form" to st.form, "field" to st.field, "fieldType" to st.type))
        forms.clear()
    }

    private fun keyOf(d: Map<String, Any?>?): String = if (d == null) "" else Json.write(d)

    companion object {
        const val RAGE_CLICKS = 3
        const val RAGE_WINDOW_MS = 1000L
        const val DEAD_WINDOW_MS = 1000L
        const val DEAD_DEDUPE_MS = 5000L
        const val ERROR_WINDOW_MS = 2000L
        const val LOOP_WINDOW_MS = 30_000L
        const val FORM_SENT_MS = 1500L
        const val SLOW_MS = 500L
        const val SLOW_DEDUPE_MS = 10_000L
        const val MAX_UX = 50

        /** `rage_click on MaterialButton#pay` (as the JS SDK words it). */
        fun message(type: String, data: Map<String, Any?>): String {
            @Suppress("UNCHECKED_CAST")
            val el = data["element"] as? Map<String, Any?>
            val what = if (el != null) (el["tag"]?.toString() ?: "") + (el["id"]?.let { "#$it" } ?: "") else ""
            return (type + if (what.isNotEmpty()) " on $what" else "").take(200)
        }
    }
}
