package com.afribase.watch

import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.Window
import com.afribase.watch.replay.Kind
import com.afribase.watch.replay.Masking
import com.afribase.watch.replay.ViewWalker

/**
 * Wraps an Activity window's callback to see touches before the app does.
 * Everything else is passed through untouched; the event itself is never
 * changed or consumed.
 */
internal class WatchWindowCallback(
    val delegate: Window.Callback,
    private val onTouch: (MotionEvent) -> Unit,
    private val onKey: (KeyEvent) -> Unit = {},
) : Window.Callback by delegate {
    override fun dispatchKeyEvent(event: KeyEvent?): Boolean {
        if (event != null) {
            try {
                onKey(event)
            } catch (_: Throwable) {
            }
        }
        return delegate.dispatchKeyEvent(event)
    }

    override fun dispatchTouchEvent(event: MotionEvent?): Boolean {
        if (event != null) {
            try {
                onTouch(event)
            } catch (_: Throwable) {
            }
        }
        return delegate.dispatchTouchEvent(event)
    }
}

/** Finds and describes the view under a tap (structure only). */
internal object ViewFinder {
    private val loc = IntArray(2)

    /** The deepest visible view at raw (x, y) px, or its nearest clickable ancestor. */
    fun at(root: View, x: Float, y: Float): View? {
        var hit: View? = null
        var v: View? = root
        var depth = 0
        while (v != null && depth < 60) {
            if (!contains(v, x, y)) break
            hit = v
            if (v !is ViewGroup) break
            var next: View? = null
            // Topmost child first.
            for (i in v.childCount - 1 downTo 0) {
                val c = v.getChildAt(i) ?: continue
                if (c.visibility == View.VISIBLE && contains(c, x, y)) {
                    next = c
                    break
                }
            }
            v = next
            depth++
        }
        var c = hit
        while (c != null) {
            if (c.isClickable) return c
            c = c.parent as? View
        }
        return hit
    }

    private fun contains(v: View, x: Float, y: Float): Boolean {
        v.getLocationOnScreen(loc)
        return x >= loc[0] && y >= loc[1] && x < loc[0] + v.width && y < loc[1] + v.height
    }

    /**
     * `{tag, kind, id, text?}`: class, wireframe kind and resource id name.
     * Button text only when the view is unmasked or maskAllText is off; never
     * text of an input.
     */
    fun describe(v: View?, maskAllText: Boolean): Map<String, Any?>? {
        if (v == null) return null
        val m = LinkedHashMap<String, Any?>()
        m["tag"] = v.javaClass.simpleName.ifEmpty { v.javaClass.name }.take(40)
        val kind = if (Markers.isBlocked(v)) Kind.BLOCKED else ViewWalker.kindOf(v)
        m["kind"] = kind
        if (v.id != View.NO_ID) {
            try {
                m["id"] = v.resources.getResourceEntryName(v.id).take(40)
            } catch (_: Exception) {
            }
        }
        if (kind == Kind.BUTTON && v is android.widget.TextView && (!maskAllText || unmasked(v))) {
            Masking.cap(v.text)?.trim()?.takeIf { it.isNotEmpty() }?.let { m["text"] = it }
        }
        return m
    }

    private fun unmasked(v: View): Boolean {
        var c: View? = v
        while (c != null) {
            if (Markers.isUnmasked(c)) return true
            c = c.parent as? View
        }
        return false
    }

    /** `MaterialButton 'Pay'`, `MaterialButton#pay` or `MaterialButton`. */
    fun label(d: Map<String, Any?>?): String {
        if (d == null) return "view"
        var s = d["tag"]?.toString() ?: "view"
        val text = d["text"]
        val id = d["id"]
        s += when {
            text != null -> " '$text'"
            id != null -> "#$id"
            else -> ""
        }
        return s.take(80)
    }
}
