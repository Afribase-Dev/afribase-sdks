package com.afribase.watch.replay

import com.afribase.watch.Json

/** One recorded event, already rendered to JSON (off the main thread). */
internal class BufferedEvent(val t: Long, val type: String, val json: String)

/**
 * The rolling replay buffer: the last 60 s of wireframe events, always
 * starting at a `snapshot`. Events before the first snapshot are dropped
 * (a player cannot draw them). Thread-safe.
 */
internal class ReplayBuffer(
    private val windowMs: Long = WINDOW_MS,
    private val maxEvents: Int = MAX_EVENTS,
) {
    private val events = ArrayList<BufferedEvent>(512)

    @Synchronized
    fun add(e: BufferedEvent, now: Long = e.t) {
        if (events.isEmpty() && e.type != TYPE_SNAPSHOT) return
        events.add(e)
        trim(now)
    }

    @Synchronized
    fun size(): Int = events.size

    @Synchronized
    fun clear() = events.clear()

    /** The buffered events: within the window, starting at a snapshot. */
    @Synchronized
    fun events(now: Long): List<BufferedEvent> {
        trim(now)
        return ArrayList(events)
    }

    /**
     * Drops events older than the window, keeping the newest snapshot taken
     * at or before the window start so the buffer still opens with one.
     */
    private fun trim(now: Long) {
        if (events.isEmpty()) return
        val start = now - windowMs
        var cut = -1
        for (i in events.indices) {
            val e = events[i]
            if (e.t > start) break
            if (e.type == TYPE_SNAPSHOT) cut = i
        }
        if (cut > 0) events.subList(0, cut).clear()
        if (events.size > maxEvents) {
            // Too many: start at the first snapshot past the overflow, or empty.
            val over = events.size - maxEvents
            var next = -1
            for (i in over until events.size) {
                if (events[i].type == TYPE_SNAPSHOT) {
                    next = i
                    break
                }
            }
            if (next < 0) events.clear() else events.subList(0, next).clear()
        }
    }

    companion object {
        const val TYPE_SNAPSHOT = "snapshot"
        const val WINDOW_MS = 60_000L
        const val MAX_EVENTS = 40_000
    }
}

/** When a walk becomes a `snapshot` event: tree changed, or 10 s keyframe. */
internal class SnapshotPolicy(private val keyframeMs: Long = KEYFRAME_MS) {
    private var lastHash: Int? = null
    private var lastScreen: String? = null
    private var lastEmit = 0L

    @Synchronized
    fun shouldEmit(hash: Int, screen: String, now: Long): Boolean {
        val emit = lastHash != hash || lastScreen != screen || now - lastEmit >= keyframeMs
        if (emit) {
            lastHash = hash
            lastScreen = screen
            lastEmit = now
        }
        return emit
    }

    @Synchronized
    fun reset() {
        lastHash = null
        lastScreen = null
        lastEmit = 0L
    }

    companion object {
        const val KEYFRAME_MS = 10_000L
    }
}

/**
 * Upload rules: one upload 5 s after an `error` or `ux` event, at most one
 * per 30 s per session and 10 per session per app launch.
 */
internal class UploadGate(
    private val throttleMs: Long = THROTTLE_MS,
    private val maxPerLaunch: Int = MAX_PER_LAUNCH,
) {
    private var lastScheduled = 0L
    private var uploads = 0
    private var pending = false

    /** True when an upload should be scheduled now (caller waits DELAY_MS). */
    @Synchronized
    fun tryTrigger(now: Long): Boolean {
        if (pending) return false
        if (uploads >= maxPerLaunch) return false
        if (lastScheduled != 0L && now - lastScheduled < throttleMs) return false
        lastScheduled = now
        uploads++
        pending = true
        return true
    }

    /** The scheduled upload ran (or was dropped). */
    @Synchronized
    fun done() {
        pending = false
    }

    /** A new session (e.g. after a long time in the background). */
    @Synchronized
    fun newSession() {
        lastScheduled = 0L
    }

    @Synchronized
    fun count(): Int = uploads

    companion object {
        const val DELAY_MS = 5_000L
        const val THROTTLE_MS = 30_000L
        const val MAX_PER_LAUNCH = 10
        const val MAX_BODY_BYTES = 10 * 1024 * 1024
    }
}

/** Metadata of an upload body (watch-wireframe-contract.md, SDK -> server). */
internal class ReplayMeta(
    val key: String,
    val sessionId: String,
    val user: String?,
    val release: String?,
    val environment: String?,
    val screen: String,
    val device: Map<String, Any?>,
    val trigger: String,
)

internal object ReplayPayload {
    fun build(meta: ReplayMeta, events: List<BufferedEvent>): String {
        val sb = StringBuilder(64 * 1024)
        sb.append('{')
        field(sb, "key", meta.key, first = true)
        field(sb, "sessionId", meta.sessionId)
        meta.user?.let { field(sb, "user", it) }
        meta.release?.let { field(sb, "release", it) }
        meta.environment?.let { field(sb, "environment", it) }
        field(sb, "format", "wireframe")
        field(sb, "platform", "android")
        field(sb, "url", "app://" + meta.screen)
        sb.append(",\"device\":"); Json.write(sb, meta.device)
        field(sb, "trigger", meta.trigger)
        sb.append(",\"startedAt\":").append(events.first().t)
        sb.append(",\"endedAt\":").append(events.last().t)
        sb.append(",\"events\":[")
        for (i in events.indices) {
            if (i > 0) sb.append(',')
            sb.append(events[i].json)
        }
        sb.append("]}")
        return sb.toString()
    }

    /** The events from the snapshot nearest the middle on: a smaller body. */
    fun halve(events: List<BufferedEvent>): List<BufferedEvent>? {
        if (events.size < 2) return null
        val mid = events.size / 2
        for (i in mid until events.size) {
            if (events[i].type == ReplayBuffer.TYPE_SNAPSHOT) return events.subList(i, events.size)
        }
        for (i in mid - 1 downTo 1) {
            if (events[i].type == ReplayBuffer.TYPE_SNAPSHOT) return events.subList(i, events.size)
        }
        return null
    }

    private fun field(sb: StringBuilder, k: String, v: String, first: Boolean = false) {
        if (!first) sb.append(',')
        Json.string(sb, k)
        sb.append(':')
        Json.string(sb, v)
    }
}
