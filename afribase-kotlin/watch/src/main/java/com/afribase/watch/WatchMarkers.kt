@file:JvmName("WatchMarkers")

package com.afribase.watch

import android.view.View

/**
 * Replay markers for Views. From XML you can also set `android:tag` to
 * `watchBlock`, `watchUnmask` or `watchSecureScreen`.
 *
 * Kotlin: `cardForm.watchBlock()`. Java: `WatchMarkers.watchBlock(cardForm)`.
 */

/** Sends this view as one `blocked` box: no children, no text. */
fun <T : View> T.watchBlock(): T = apply { setTag(R.id.afribase_watch_block, true) }

/** Sends the real text of this view and its children (inputs stay masked). */
fun <T : View> T.watchUnmask(): T = apply { setTag(R.id.afribase_watch_unmask, true) }

/** Treats the whole screen holding this view as secure: no wireframe at all. */
fun <T : View> T.watchSecureScreen(): T = apply { setTag(R.id.afribase_watch_secure_screen, true) }

internal object Markers {
    const val BLOCK = "watchBlock"
    const val UNMASK = "watchUnmask"
    const val SECURE = "watchSecureScreen"

    fun isBlocked(v: View): Boolean = v.getTag(R.id.afribase_watch_block) == true || v.tag == BLOCK
    fun isUnmasked(v: View): Boolean = v.getTag(R.id.afribase_watch_unmask) == true || v.tag == UNMASK
    fun isSecure(v: View): Boolean = v.getTag(R.id.afribase_watch_secure_screen) == true || v.tag == SECURE
}
