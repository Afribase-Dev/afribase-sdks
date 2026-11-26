package com.afribase.watch.replay

import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.WebView
import android.widget.AbsListView
import android.widget.Button
import android.widget.CompoundButton
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.ScrollView
import android.widget.TextView
import com.afribase.watch.Markers
import java.util.WeakHashMap

/** Stable ids for views (and Compose semantics nodes) during the session. */
internal class NodeIds {
    private val views = WeakHashMap<Any, Int>()
    private val compose = HashMap<Long, Int>()
    private var next = 1

    fun of(v: Any): Int = views[v] ?: next++.also { views[v] = it }

    fun ofSemantics(rootId: Int, semanticsId: Int): Int {
        if (compose.size > 50_000) compose.clear()
        val key = (rootId.toLong() shl 32) or (semanticsId.toLong() and 0xffffffffL)
        return compose[key] ?: next++.also { compose[key] = it }
    }
}

/** State of one walk. */
internal class WalkContext(
    val density: Float,
    val screenWpx: Int,
    val screenHpx: Int,
    val maskAllText: Boolean,
    val ids: NodeIds,
    val deadlineNanos: Long,
    val nanoTime: () -> Long = System::nanoTime,
    val maskAllInputs: Boolean = false,
) {
    var nodes = 0
    var truncated = false
    var secureMarker = false
    var hash = 17
    /** Scroll offsets (px) of scroll containers by node id. */
    val scrolls = HashMap<Int, Long>()

    fun full(): Boolean {
        if (nodes >= MAX_NODES) {
            truncated = true
            return true
        }
        // Cheap check every 64 nodes: over the hard time cap, stop.
        if (nodes > 0 && nodes and 63 == 0 && nanoTime() > deadlineNanos) {
            truncated = true
            return true
        }
        return false
    }

    fun dp(px: Float): Float = px / density

    fun onScreen(left: Float, top: Float, w: Int, h: Int): Boolean =
        left + w > 0 && top + h > 0 && left < screenWpx && top < screenHpx

    companion object {
        const val MAX_DEPTH = 60
        const val MAX_NODES = 3000
    }
}

/** Walks Compose content inside a View (implemented only when Compose is present). */
internal interface ComposeBridge {
    fun isComposeRoot(v: View): Boolean

    /** The nodes for a Compose root at (leftPx, topPx) on screen. */
    fun walk(v: View, leftPx: Float, topPx: Float, unmasked: Boolean, masked: Boolean, depth: Int, ctx: WalkContext): List<WireNode>
}

/**
 * Turns a window's View tree into wireframe nodes. Main thread only. Reads
 * view geometry, class, text and simple backgrounds; never draws anything.
 */
internal class ViewWalker(private val compose: ComposeBridge?) {

    /**
     * @param windowFlags the window's `WindowManager.LayoutParams.flags`.
     * @param origin the root's location on screen in px.
     */
    fun walk(
        screen: String,
        root: View,
        windowFlags: Int,
        origin: IntArray,
        ctx: WalkContext,
    ): WalkResult {
        val wDp = ctx.dp(ctx.screenWpx.toFloat())
        val hDp = ctx.dp(ctx.screenHpx.toFloat())
        if (windowFlags and WindowManager.LayoutParams.FLAG_SECURE != 0 || Markers.isSecure(root)) {
            return WalkResult(screen, wDp, hDp, secure = true, root = null, truncated = false, hash = SECURE_HASH, nodes = 0)
        }
        val node = visit(root, origin[0].toFloat(), origin[1].toFloat(), false, 0, ctx, isRoot = true)
        if (ctx.secureMarker) {
            return WalkResult(screen, wDp, hDp, secure = true, root = null, truncated = false, hash = SECURE_HASH, nodes = 0)
        }
        return WalkResult(screen, wDp, hDp, false, node, ctx.truncated, ctx.hash, ctx.nodes)
    }

    /** One view and its subtree; null when it is skipped. [left]/[top]: px on screen. */
    private fun visit(v: View, left: Float, top: Float, parentUnmasked: Boolean, depth: Int, ctx: WalkContext, isRoot: Boolean = false, parentMasked: Boolean = false): WireNode? {
        if (ctx.secureMarker) return null
        if (Markers.isSecure(v)) {
            ctx.secureMarker = true
            return null
        }
        if (v.visibility != View.VISIBLE) return null
        val w = v.width
        val h = v.height
        if (w <= 0 || h <= 0) return null
        if (v.alpha <= 0f) return null
        if (!ctx.onScreen(left, top, w, h)) return null
        if (ctx.full()) return null

        val unmasked = parentUnmasked || Markers.isUnmasked(v)
        val masked = parentMasked || Markers.isMasked(v)
        val id = ctx.ids.of(v)
        ctx.nodes++

        if (Markers.isBlocked(v)) {
            return finish(WireNode(id, Kind.BLOCKED, ctx.dp(left), ctx.dp(top), ctx.dp(w.toFloat()), ctx.dp(h.toFloat())), ctx)
        }
        if (v is WebView) {
            return finish(WireNode(id, Kind.WEB, ctx.dp(left), ctx.dp(top), ctx.dp(w.toFloat()), ctx.dp(h.toFloat())), ctx)
        }

        val node = WireNode(id, kindOf(v), ctx.dp(left), ctx.dp(top), ctx.dp(w.toFloat()), ctx.dp(h.toFloat()))
        if (v.alpha < 1f) node.a = v.alpha
        background(v.background, node, ctx)

        if (v is TextView) {
            val input = v is EditText || v.isTextEditable()
            val secret = input && isSecret(v) || v.transformationMethod is PasswordTransformationMethod
            node.fg = hex(v.currentTextColor)
            val raw = v.text
            if (secret) {
                Masking.apply(node, Masking.SECRET)
            } else if (!raw.isNullOrEmpty()) {
                Masking.apply(node, Masking.textFor(raw, input, false, unmasked, ctx.maskAllText, ctx.maskAllInputs, masked))
            }
        }

        if (node.k == Kind.LIST && (v is ScrollView || v is HorizontalScrollView || isNestedScroll(v))) {
            ctx.scrolls[id] = (v.scrollX.toLong() shl 32) or (v.scrollY.toLong() and 0xffffffffL)
        }

        if (compose != null && compose.isComposeRoot(v)) {
            if (depth < WalkContext.MAX_DEPTH) {
                for (c in compose.walk(v, left, top, unmasked, masked, depth + 1, ctx)) node.add(c)
            }
        } else if (v is ViewGroup && depth < WalkContext.MAX_DEPTH) {
            val sx = v.scrollX
            val sy = v.scrollY
            for (i in 0 until v.childCount) {
                val c = v.getChildAt(i) ?: continue
                val cl = left + c.left - sx + c.translationX
                val ct = top + c.top - sy + c.translationY
                val child = visit(c, cl, ct, unmasked, depth + 1, ctx, parentMasked = masked) ?: continue
                hoistInto(node, child)
                if (ctx.secureMarker) return null
            }
        }
        if (isRoot) return finish(node, ctx)
        return finish(node, ctx)
    }

    private fun finish(n: WireNode, ctx: WalkContext): WireNode {
        ctx.hash = 31 * ctx.hash + n.hash()
        return n
    }

    companion object {
        const val SECURE_HASH = 0x5ec0e

        private val kindCache = HashMap<Class<*>, String>()

        /**
         * Adds [child] to [parent], or, when the child is a bare container
         * (plain view, no background, no text, fully opaque), its children
         * instead: coordinates are screen-relative, so nothing moves.
         */
        fun hoistInto(parent: WireNode, child: WireNode) {
            val kids = child.children
            if (child.k == Kind.VIEW && child.bg == null && child.r == 0f && child.a >= 1f &&
                child.text == null && !child.textNull && kids != null && kids.isNotEmpty()
            ) {
                for (k in kids) parent.add(k)
            } else {
                parent.add(child)
            }
        }

        fun kindOf(v: View): String {
            return when {
                v is WebView -> Kind.WEB
                v is EditText -> Kind.INPUT
                v is CompoundButton -> Kind.SWITCH
                v is Button || v is ImageButton -> Kind.BUTTON
                v is TextView -> if (v.isTextEditable()) Kind.INPUT else Kind.TEXT
                v is ImageView -> if (v.isClickable) Kind.BUTTON else Kind.IMAGE
                v is AbsListView || v is ScrollView || v is HorizontalScrollView -> Kind.LIST
                v is ViewGroup -> kindByName(v.javaClass) ?: Kind.VIEW
                v.isClickable -> Kind.BUTTON
                else -> Kind.VIEW
            }
        }

        private fun TextView.isTextEditable(): Boolean = onCheckIsTextEditor() && isEnabled && keyListener != null

        /** androidx lists, found by class name so the SDK needs no androidx dependency. */
        private fun kindByName(cls: Class<*>): String? {
            kindCache[cls]?.let { return if (it.isEmpty()) null else it }
            var c: Class<*>? = cls
            var out = ""
            while (c != null && c != ViewGroup::class.java) {
                when (c.name) {
                    "androidx.recyclerview.widget.RecyclerView",
                    "androidx.core.widget.NestedScrollView",
                    "androidx.viewpager.widget.ViewPager",
                    -> {
                        out = Kind.LIST
                        break
                    }
                }
                c = c.superclass
            }
            kindCache[cls] = out
            return if (out.isEmpty()) null else out
        }

        private fun isNestedScroll(v: View): Boolean {
            var c: Class<*>? = v.javaClass
            while (c != null && c != ViewGroup::class.java) {
                if (c.name == "androidx.core.widget.NestedScrollView") return true
                c = c.superclass
            }
            return false
        }

        private val SECRET_HINTS = arrayOf("password", "otp", "creditcard", "securitycode", "cvv", "cvc", "pin")
        private val SECRET_NAMES = arrayOf("password", "passwd", "otp", "cvv", "cvc", "card", "pin")

        /** Password, one-time-code and card fields: text and length never sent. */
        fun isSecret(tv: TextView): Boolean {
            val type = tv.inputType
            val cls = type and InputType.TYPE_MASK_CLASS
            val variation = type and InputType.TYPE_MASK_VARIATION
            if (cls == InputType.TYPE_CLASS_TEXT && (
                    variation == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
                        variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
                        variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
                    )
            ) return true
            if (cls == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD) return true
            if (tv.transformationMethod is PasswordTransformationMethod) return true
            if (Build.VERSION.SDK_INT >= 26) {
                val hints = tv.autofillHints
                if (hints != null) {
                    for (h in hints) {
                        val l = h.lowercase()
                        if (SECRET_HINTS.any { l.contains(it) }) return true
                    }
                }
            }
            if (tv.id != View.NO_ID) {
                val name = try {
                    tv.resources.getResourceEntryName(tv.id).lowercase()
                } catch (_: Exception) {
                    null
                }
                if (name != null && SECRET_NAMES.any { name.contains(it) }) return true
            }
            return false
        }

        fun background(d: Drawable?, node: WireNode, ctx: WalkContext) {
            when (d) {
                is ColorDrawable -> {
                    val c = d.color
                    if ((c ushr 24) >= 26) node.bg = hex(c)
                }
                is GradientDrawable -> {
                    if (Build.VERSION.SDK_INT >= 24) {
                        val c = d.color?.defaultColor
                        if (c != null && (c ushr 24) >= 26) node.bg = hex(c)
                        try {
                            val r = d.cornerRadius
                            if (r > 0f) node.r = ctx.dp(r)
                        } catch (_: Throwable) {
                        }
                    }
                }
            }
        }

        fun hex(color: Int): String {
            val rgb = color and 0xffffff
            val s = Integer.toHexString(rgb).uppercase()
            return "#" + "000000".substring(s.length) + s
        }
    }
}
