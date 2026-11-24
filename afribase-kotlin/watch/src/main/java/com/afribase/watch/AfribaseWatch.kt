package com.afribase.watch

import android.content.Context
import android.util.Log

/**
 * Base1 Watch for Android: crashes and errors, UX signals, live presence
 * and (opt-in) wireframe session replay.
 *
 *     class App : Application() {
 *         override fun onCreate() {
 *             super.onCreate()
 *             AfribaseWatch.init(this, WatchConfig(key = "abw_...", endpoint = "https://api.example.com/watch/ingest"))
 *         }
 *     }
 *
 * Every call is safe before init (a no-op) and never throws.
 */
object AfribaseWatch {
    @Volatile private var client: WatchClient? = null

    /** Starts Watch once; later calls are ignored. Call from Application.onCreate. */
    @JvmStatic
    fun init(context: Context, config: WatchConfig) {
        if (config.key.isBlank() || config.endpoint.isBlank()) return
        synchronized(this) {
            if (client != null) return
            try {
                val c = WatchClient(context, config)
                c.start()
                client = c
            } catch (t: Throwable) {
                Log.w(WatchClient.TAG, "Watch failed to start", t)
            }
        }
    }

    /** Reports a caught error (captureError in the JS SDK). Sampled by `sampleRate`. */
    @JvmStatic
    @JvmOverloads
    fun captureError(t: Throwable, context: Map<String, Any?>? = null) {
        client?.captureError(t, context)
    }

    /** Same as [captureError]. */
    @JvmStatic
    @JvmOverloads
    fun captureException(t: Throwable, context: Map<String, Any?>? = null) {
        client?.captureError(t, context)
    }

    /** A `log` event: something worth seeing in Watch that is not an exception. */
    @JvmStatic
    @JvmOverloads
    fun log(message: String, context: Map<String, Any?>? = null) {
        client?.log(message, context)
    }

    /**
     * Names the current screen (`app://<name>`) for single-Activity apps
     * (Compose navigation, fragments). Activities are named automatically.
     */
    @JvmStatic
    fun setScreen(name: String) {
        client?.setScreen(name)
    }

    /** Adds a breadcrumb sent with the next events (no personal data, please). */
    @JvmStatic
    fun addBreadcrumb(type: String, data: Map<String, Any?> = emptyMap()) {
        client?.breadcrumb(type, data)
    }

    /** The session id: send it to your backend as `X-Watch-Session` (see [WatchInterceptor]). */
    @JvmStatic
    val sessionId: String?
        get() = client?.sessionId

    /** Sends queued events now (in the background). */
    @JvmStatic
    fun flush() {
        client?.flush()
    }

    /** Stops Watch and restores the previous crash handler. */
    @JvmStatic
    fun stop() {
        synchronized(this) {
            client?.stop()
            client = null
        }
    }

    internal fun current(): WatchClient? = client
}
