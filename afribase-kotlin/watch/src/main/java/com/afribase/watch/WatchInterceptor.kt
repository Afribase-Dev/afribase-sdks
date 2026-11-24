package com.afribase.watch

import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException

/**
 * OkHttp interceptor (the JS SDK's fetch wrapper on Android):
 * - adds `X-Watch-Session: <sessionId>` so Watch can link a backend error
 *   (Python SDK) to this app session;
 * - records each request as a breadcrumb (method, URL without query, status, ms);
 * - reports 5xx responses and network failures as `http` events, and
 *   requests slower than 4 s as `slow` events;
 * - tells the UX signals a request happened (dead taps, form submission).
 * Bodies and headers are never read.
 *
 *     OkHttpClient.Builder().addInterceptor(WatchInterceptor()).build()
 *
 * OkHttp is not a dependency of the SDK; this class is only usable when your
 * app has OkHttp 4.
 *
 * @param captureHttp false: only add the header.
 */
class WatchInterceptor @JvmOverloads constructor(private val captureHttp: Boolean = true) : Interceptor {
    @Throws(IOException::class)
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        val sid = AfribaseWatch.sessionId
        val out = if (sid != null && req.header(HEADER) == null) req.newBuilder().header(HEADER, sid).build() else req
        val client = AfribaseWatch.current()
        if (!captureHttp || client == null) return chain.proceed(out)

        val started = System.currentTimeMillis()
        val method = out.method.uppercase()
        val url = Urls.stripQuery(out.url.toString())
        try {
            val res = chain.proceed(out)
            note(client, method, url, res.code, System.currentTimeMillis() - started, null)
            return res
        } catch (e: IOException) {
            note(client, method, url, 0, System.currentTimeMillis() - started, e.message?.take(100) ?: e.javaClass.simpleName)
            throw e
        }
    }

    private fun note(client: WatchClient, method: String, url: String, status: Int, ms: Long, failure: String?) {
        try {
            client.noteRequest(method, url, status, ms, failure)
        } catch (_: Throwable) {
        }
    }

    companion object {
        const val HEADER = "X-Watch-Session"
    }
}
