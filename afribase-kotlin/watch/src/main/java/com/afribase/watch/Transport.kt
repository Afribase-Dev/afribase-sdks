package com.afribase.watch

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.zip.GZIPOutputStream

/** Sends one body; returns the HTTP status, or -1 on a network error. Worker thread only. */
internal interface Transport {
    fun post(url: String, body: ByteArray, key: String): Int
}

internal class HttpTransport(private val timeoutMs: Int = 10_000) : Transport {
    override fun post(url: String, body: ByteArray, key: String): Int {
        var conn: HttpURLConnection? = null
        return try {
            conn = URL(url).openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = timeoutMs
            conn.readTimeout = timeoutMs
            conn.doOutput = true
            conn.useCaches = false
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("X-Watch-Key", key)
            conn.setFixedLengthStreamingMode(body.size)
            conn.outputStream.use { it.write(body) }
            val code = conn.responseCode
            try {
                (if (code >= 400) conn.errorStream else conn.inputStream)?.use { s ->
                    val buf = ByteArray(1024)
                    while (s.read(buf) >= 0) { /* drain so the connection can be reused */ }
                }
            } catch (_: Exception) {
            }
            code
        } catch (_: Throwable) {
            -1
        } finally {
            try {
                conn?.disconnect()
            } catch (_: Throwable) {
            }
        }
    }
}

internal object Urls {
    /** .../watch/ingest?x=y -> .../watch/ingest/<sub>?x=y&key=... (as watchSubURL in the JS SDK). */
    fun sub(endpoint: String, sub: String, key: String): String {
        val i = endpoint.indexOf('?')
        val base = (if (i >= 0) endpoint.substring(0, i) else endpoint).trimEnd('/')
        val query = if (i >= 0) endpoint.substring(i + 1) else ""
        return base + "/" + sub + "?" + (if (query.isNotEmpty()) "$query&" else "") + "key=" + URLEncoder.encode(key, "UTF-8")
    }

    fun ingest(endpoint: String, key: String): String =
        endpoint + (if (endpoint.contains('?')) "&" else "?") + "key=" + URLEncoder.encode(key, "UTF-8")

    /** Drops query and fragment: no tokens in breadcrumbs. */
    fun stripQuery(u: String): String {
        val i = u.indexOfAny(charArrayOf('?', '#'))
        return if (i >= 0) u.substring(0, i) else u
    }
}

internal object Gzip {
    fun encode(s: String): ByteArray {
        val bos = ByteArrayOutputStream(maxOf(256, s.length / 6))
        GZIPOutputStream(bos).use { it.write(s.toByteArray(Charsets.UTF_8)) }
        return bos.toByteArray()
    }
}

/** 2xx: sent. 4xx other than 408/429: the server will never take it. Either way, drop it. */
internal fun deliveredOrRejected(code: Int): Boolean =
    code in 200..299 || (code in 400..499 && code != 408 && code != 429)
