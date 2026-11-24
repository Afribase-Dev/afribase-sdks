package com.afribase.watch

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The last 30 breadcrumbs. Thread-safe. Values are cleaned one by one
 * ([CrumbMask]) so times and statuses stay readable; the server masks every
 * string leaf again.
 */
internal class Breadcrumbs(private val max: Int = 30) {
    private val items = ArrayDeque<Map<String, Any?>>()

    @Synchronized
    fun add(type: String, data: Map<String, Any?>, t: Long = System.currentTimeMillis()) {
        val m = LinkedHashMap<String, Any?>(data.size + 2)
        m["t"] = t
        m["type"] = type
        for ((k, v) in data) m[k] = CrumbMask.value(k, v)
        items.addLast(m)
        while (items.size > max) items.removeFirst()
    }

    @Synchronized
    fun snapshot(): List<Map<String, Any?>> = ArrayList(items)
}

/** Static facts sent with every event. */
internal class EventEnv(
    val release: String?,
    val environment: String?,
    val os: String,
    val model: String,
    val sdkVersion: String,
)

/**
 * Builds events in the shape the JS SDK sends to `POST /watch/ingest`
 * (service.WatchIngestEvent), plus `platform: "android"`.
 */
internal object EventBuilder {
    const val MAX_MESSAGE = 2000
    const val MAX_STACK = 16_000

    fun base(
        kind: String,
        message: String,
        env: EventEnv,
        sessionId: String,
        userId: String?,
        screen: String?,
        crumbs: List<Map<String, Any?>>,
        context: Map<String, Any?>?,
        now: Long,
    ): LinkedHashMap<String, Any?> {
        val m = LinkedHashMap<String, Any?>()
        m["kind"] = kind
        m["message"] = message.take(MAX_MESSAGE)
        m["url"] = screenUrl(screen)
        m["release"] = env.release
        m["environment"] = env.environment
        m["userId"] = userId
        m["sessionId"] = sessionId
        m["platform"] = "android"
        m["breadcrumbs"] = crumbs
        val ctx = LinkedHashMap<String, Any?>()
        ctx["platform"] = "android"
        ctx["os"] = env.os
        ctx["device"] = env.model
        ctx["sdk"] = "afribase-kotlin/" + env.sdkVersion
        if (context != null) ctx.putAll(context)
        m["context"] = ctx
        m["timestamp"] = iso(now)
        return m
    }

    fun error(
        t: Throwable,
        fatal: Boolean,
        thread: String?,
        env: EventEnv,
        sessionId: String,
        userId: String?,
        screen: String?,
        crumbs: List<Map<String, Any?>>,
        context: Map<String, Any?>?,
        now: Long,
    ): LinkedHashMap<String, Any?> {
        val ctx = LinkedHashMap<String, Any?>()
        ctx["fatal"] = fatal
        if (thread != null) ctx["thread"] = thread
        if (context != null) ctx.putAll(context)
        val m = base("error", message(t), env, sessionId, userId, screen, crumbs, ctx, now)
        m["stack"] = stack(t)
        return m
    }

    /** `java.lang.IllegalStateException: boom`, like `TypeError: boom` on the web. */
    fun message(t: Throwable): String = t.toString().take(MAX_MESSAGE)

    fun stack(t: Throwable): String = try {
        t.stackTraceToString().take(MAX_STACK)
    } catch (_: Throwable) {
        t.toString()
    }

    fun screenUrl(screen: String?): String = "app://" + (screen ?: "unknown")

    fun iso(t: Long): String {
        val f = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        f.timeZone = TimeZone.getTimeZone("UTC")
        return f.format(Date(t))
    }

    /** `{"events":[...]}` from already-rendered events. */
    fun batch(events: List<String>): String {
        val sb = StringBuilder(events.sumOf { it.length } + 16)
        sb.append("{\"events\":[")
        events.forEachIndexed { i, e ->
            if (i > 0) sb.append(',')
            sb.append(e)
        }
        sb.append("]}")
        return sb.toString()
    }
}


/**
 * Breadcrumb values, value by value (as the server's maskJSONLeaves): a
 * value under a secret name (password, token, api key ...) is replaced whole;
 * URL-looking strings lose their query and fragment; strings are capped at
 * 300 characters. Keys, numbers and booleans are kept.
 */
internal object CrumbMask {
    const val DOTS = "\u2022\u2022\u2022\u2022"
    private val SECRET = Regex("(?i)(password|passwd|pwd|passphrase|secret|token|api[_-]?key|apikey|private[_-]?key|access[_-]?key|credential|authorization|cookie)")
    private val SAFE = setOf("tokens", "max_tokens", "token_count", "keyboard", "keys", "keyword", "keywords")
    private val URL = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://")

    fun value(key: String, v: Any?): Any? {
        val secret = key.isNotEmpty() && SECRET.containsMatchIn(key) && key.lowercase() !in SAFE
        return when (v) {
            null -> null
            is Map<*, *> -> LinkedHashMap<String, Any?>().also { out -> for ((k, c) in v) out[k.toString()] = value(k.toString(), c) }
            is List<*> -> v.map { value(key, it) }
            is String -> if (secret && v.isNotBlank()) DOTS else clean(v)
            is Number -> if (secret) DOTS else v
            is Boolean -> v
            else -> if (secret) DOTS else clean(v.toString())
        }
    }

    private fun clean(s: String): String {
        val u = if (URL.containsMatchIn(s) || (s.startsWith("/") && s.contains('?'))) Urls.stripQuery(s) else s
        return u.take(300)
    }
}
