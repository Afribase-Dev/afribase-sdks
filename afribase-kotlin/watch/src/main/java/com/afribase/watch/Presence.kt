package com.afribase.watch

import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Live presence (as watch-presence.ts): a heartbeat every 15 s while the app
 * is in the foreground, soon after a screen change (server allows 1 per 2 s),
 * and `leaving: true` when the app goes to the background. `path` is
 * `app://<Screen>`. Actions are the last 5 taps and screen changes,
 * described by view class and id, never by what was typed.
 */
internal class Presence(
    private val url: String,
    private val key: String,
    private val release: String?,
    private val sessionId: () -> String,
    private val user: () -> String?,
    private val transport: Transport,
    private val worker: ScheduledExecutorService,
    private val now: () -> Long = System::currentTimeMillis,
    private val title: () -> String = { "" },
) {
    private val actions = ArrayList<Map<String, Any?>>()
    @Volatile private var screen: String? = null
    @Volatile private var foreground = false
    @Volatile private var stopped = false
    private var lastSent = 0L
    private var deferred: ScheduledFuture<*>? = null
    private var timer: ScheduledFuture<*>? = null

    @Synchronized
    fun addAction(type: String, label: String) {
        actions.add(mapOf("t" to now(), "type" to type, "label" to label.take(80)))
        while (actions.size > MAX_ACTIONS) actions.removeAt(0)
    }

    fun screen(name: String) {
        if (name == screen) return
        screen = name
        addAction("navigation", name)
        if (foreground) sendSoon()
    }

    fun foreground() {
        if (stopped || foreground) return
        foreground = true
        synchronized(this) {
            timer?.cancel(false)
            timer = worker.scheduleWithFixedDelay({ sendSoon() }, INTERVAL_MS, INTERVAL_MS, TimeUnit.MILLISECONDS)
        }
        sendSoon()
    }

    fun background() {
        if (!foreground) return
        foreground = false
        synchronized(this) {
            timer?.cancel(false)
            timer = null
            deferred?.cancel(false)
            deferred = null
        }
        worker.execute { send(true) }
    }

    fun stop() {
        background()
        stopped = true
    }

    @Synchronized
    fun body(leaving: Boolean): String {
        val m = LinkedHashMap<String, Any?>()
        m["key"] = key
        m["sessionId"] = sessionId()
        m["user"] = try {
            user()
        } catch (_: Throwable) {
            null
        }
        m["release"] = release
        m["path"] = EventBuilder.screenUrl(screen)
        m["title"] = try {
            title()
        } catch (_: Throwable) {
            ""
        }
        m["actions"] = ArrayList(actions)
        m["leaving"] = leaving
        m["platform"] = "android"
        return Json.write(m)
    }

    private fun sendSoon() {
        if (stopped) return
        synchronized(this) {
            if (deferred != null) return
            val wait = lastSent + MIN_GAP_MS - now()
            if (wait > 0) {
                deferred = worker.schedule({
                    synchronized(this) { deferred = null }
                    send(false)
                }, wait, TimeUnit.MILLISECONDS)
                return
            }
        }
        worker.execute { send(false) }
    }

    private fun send(leaving: Boolean) {
        if (stopped) return
        synchronized(this) { lastSent = now() }
        try {
            transport.post(url, body(leaving).toByteArray(Charsets.UTF_8), key)
        } catch (_: Throwable) {
        }
    }

    companion object {
        const val INTERVAL_MS = 15_000L
        const val MIN_GAP_MS = 2_000L
        const val MAX_ACTIONS = 5

        private val EMAIL = Regex("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")
        private val DIGITS = Regex("\\d{4,}")

        /** Masks emails and long digit runs in a screen title (maskTitle in JS). */
        fun maskTitle(title: String): String =
            title.replace(EMAIL, "***").replace(DIGITS) { m -> "*".repeat(m.value.length) }.take(120)
    }
}
