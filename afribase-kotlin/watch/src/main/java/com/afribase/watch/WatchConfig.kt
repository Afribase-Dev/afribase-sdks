package com.afribase.watch

/**
 * Base1 Watch settings.
 *
 * @param key the target's ingest key (`abw_...`, write-only, safe in an app).
 * @param endpoint the ingest URL, e.g. `https://api.example.com/watch/ingest`.
 * @param release your app version, e.g. `1.4.2+87`.
 * @param environment e.g. `production`.
 * @param replay wireframe session replay. Off unless true here AND the target
 *   owner turns replay on in Watch settings. Never takes pixels.
 * @param live live presence heartbeats (screen and last 5 actions); the
 *   server drops them unless the target owner turns live presence on.
 * @param maskAllText replay: mask the text of every view unless a view (or an
 *   ancestor) carries `watchUnmask`. When false, plain labels are sent as is;
 *   inputs are always masked and password / one-time-code fields never sent.
 * @param ux UX signals: rage taps, slow screen loads, errors right after a tap.
 * @param sampleRate 0..1, applied to error events.
 * @param user your own user id (hashed by the server, never stored raw).
 * @param slowScreenMs a screen whose first frame takes longer than this is
 *   reported as a `slow` event.
 * @param debug log what the SDK sends to logcat (tag `AfribaseWatch`).
 */
data class WatchConfig @JvmOverloads constructor(
    val key: String,
    val endpoint: String,
    val release: String? = null,
    val environment: String? = null,
    val replay: Boolean = false,
    val live: Boolean = true,
    val maskAllText: Boolean = true,
    val ux: Boolean = true,
    val sampleRate: Double = 1.0,
    val user: (() -> String?)? = null,
    val slowScreenMs: Long = 3000,
    val debug: Boolean = false,
)
