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
 * @param maskAllText replay: opt in to mask the text of every view (inputs
 *   too) unless a view (or an ancestor) carries `watchUnmask`. Default false:
 *   text and input values are sent as shown, and only password / one-time-code
 *   / card fields are hidden (never sent, not even their length). Mark single
 *   views with `watchMask` to mask just them.
 * @param maskAllInputs replay: opt in to mask every input value (length kept).
 *   Default false.
 * @param ux UX signals: rage taps, slow screen loads, errors right after a tap.
 * @param sampleRate 0..1, applied to error events.
 * @param user your own user id (hashed by the server, never stored raw).
 * @param slowScreenMs a screen whose first frame takes longer than this is
 *   reported as a `slow` event.
 * @param debug log what the SDK sends to logcat (tag `AfribaseWatch`).
 * @param replayOnSecureWindows replay: record a wireframe even when the window
 *   has `FLAG_SECURE` (by default such windows are sent only as "secure screen"
 *   placeholders). Wireframes never contain pixels, so this does not weaken what
 *   `FLAG_SECURE` protects; those windows follow the same masking rules as any
 *   other screen (secret fields never sent). Screens marked
 *   `watchSecureScreen` stay placeholders. Default false.
 */
data class WatchConfig @JvmOverloads constructor(
    val key: String,
    val endpoint: String,
    val release: String? = null,
    val environment: String? = null,
    val replay: Boolean = false,
    val live: Boolean = true,
    val maskAllText: Boolean = false,
    val ux: Boolean = true,
    val sampleRate: Double = 1.0,
    val user: (() -> String?)? = null,
    val slowScreenMs: Long = 3000,
    val debug: Boolean = false,
    val replayOnSecureWindows: Boolean = false,
    val maskAllInputs: Boolean = false,
)
