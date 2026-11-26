package com.afribase.watch.compose

import android.view.View
import androidx.compose.ui.platform.ViewRootForTest
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsConfiguration
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import com.afribase.watch.replay.ComposeBridge
import com.afribase.watch.replay.Kind
import com.afribase.watch.replay.Masking
import com.afribase.watch.replay.ViewWalker
import com.afribase.watch.replay.WalkContext
import com.afribase.watch.replay.WireNode

/**
 * Detects Compose at runtime. Compose is a compileOnly dependency: nothing
 * in this package is loaded unless [available] is true.
 */
internal object ComposeSupport {
    val available: Boolean by lazy {
        try {
            Class.forName("androidx.compose.ui.platform.ViewRootForTest")
            Class.forName("androidx.compose.ui.semantics.SemanticsNode")
            true
        } catch (_: Throwable) {
            false
        }
    }

    fun bridge(): ComposeBridge? = if (available) {
        try {
            ComposeWalker()
        } catch (_: Throwable) {
            null
        }
    } else {
        null
    }
}

/**
 * Walks the unmerged semantics tree of a Compose root. Reads bounds, roles,
 * text and our markers; never draws.
 */
internal class ComposeWalker : ComposeBridge {
    override fun isComposeRoot(v: View): Boolean = v is ViewRootForTest

    override fun walk(v: View, leftPx: Float, topPx: Float, unmasked: Boolean, masked: Boolean, depth: Int, ctx: WalkContext): List<WireNode> {
        val root = try {
            (v as ViewRootForTest).semanticsOwner.unmergedRootSemanticsNode
        } catch (_: Throwable) {
            return emptyList()
        }
        val rootId = ctx.ids.of(v)
        val out = ArrayList<WireNode>()
        // The root semantics node covers the whole ComposeView: walk its children.
        val parent = WireNode(0, Kind.VIEW, 0f, 0f, 0f, 0f)
        if (isSecure(root.config)) {
            ctx.secureMarker = true
            return emptyList()
        }
        val rootUnmasked = unmasked || root.config.getOrNull(WatchSemantics.Unmask) == true
        val rootMasked = masked || root.config.getOrNull(WatchSemantics.Mask) == true
        for (c in root.children) {
            val n = visit(c, rootId, leftPx, topPx, rootUnmasked, depth, ctx, rootMasked) ?: continue
            ViewWalker.hoistInto(parent, n)
            if (ctx.secureMarker) return emptyList()
        }
        parent.children?.let { out.addAll(it) }
        return out
    }

    private fun isSecure(c: SemanticsConfiguration) = c.getOrNull(WatchSemantics.SecureScreen) == true

    private fun visit(n: SemanticsNode, rootId: Int, leftPx: Float, topPx: Float, parentUnmasked: Boolean, depth: Int, ctx: WalkContext, parentMasked: Boolean = false): WireNode? {
        if (ctx.secureMarker) return null
        val c = n.config
        if (isSecure(c)) {
            ctx.secureMarker = true
            return null
        }
        val info = n.layoutInfo
        if (!info.isPlaced || !info.isAttached) return null
        val b = n.boundsInRoot
        val w = b.width
        val h = b.height
        if (w <= 0f || h <= 0f) return null
        val l = leftPx + b.left
        val t = topPx + b.top
        if (!ctx.onScreen(l, t, w.toInt() + 1, h.toInt() + 1)) return null
        if (ctx.full()) return null

        val id = ctx.ids.ofSemantics(rootId, n.id)
        ctx.nodes++
        val unmasked = parentUnmasked || c.getOrNull(WatchSemantics.Unmask) == true
        val masked = parentMasked || c.getOrNull(WatchSemantics.Mask) == true
        if (c.getOrNull(WatchSemantics.Block) == true) {
            return finish(WireNode(id, Kind.BLOCKED, ctx.dp(l), ctx.dp(t), ctx.dp(w), ctx.dp(h)), ctx)
        }
        val node = WireNode(id, kindOf(c, n), ctx.dp(l), ctx.dp(t), ctx.dp(w), ctx.dp(h))

        val editable = c.getOrNull(SemanticsProperties.EditableText)
        val password = c.contains(SemanticsProperties.Password) || editable != null && secretTag(c.getOrNull(SemanticsProperties.TestTag))
        if (password) {
            Masking.apply(node, Masking.SECRET)
        } else if (editable != null) {
            if (editable.text.isNotEmpty()) Masking.apply(node, Masking.textFor(editable.text, true, false, unmasked, ctx.maskAllText, ctx.maskAllInputs, masked))
        } else {
            val texts = c.getOrNull(SemanticsProperties.Text)
            if (!texts.isNullOrEmpty()) {
                val joined = if (texts.size == 1) texts[0].text else texts.joinToString(" ") { it.text }
                if (joined.isNotEmpty()) Masking.apply(node, Masking.textFor(joined, false, false, unmasked, ctx.maskAllText, ctx.maskAllInputs, masked))
            }
        }

        if (depth < WalkContext.MAX_DEPTH) {
            for (child in n.children) {
                val cn = visit(child, rootId, leftPx, topPx, unmasked, depth + 1, ctx, masked) ?: continue
                ViewWalker.hoistInto(node, cn)
                if (ctx.secureMarker) return null
            }
        }
        return finish(node, ctx)
    }

    private fun finish(n: WireNode, ctx: WalkContext): WireNode {
        ctx.hash = 31 * ctx.hash + n.hash()
        return n
    }

    /**
     * A text field whose testTag names a secret (password, otp, pin, card,
     * cvv): Compose has no inputType, so this mirrors the View id check.
     */
    private fun secretTag(tag: String?): Boolean {
        if (tag.isNullOrEmpty()) return false
        val l = tag.lowercase()
        return SECRET_TAGS.any { l.contains(it) }
    }

    private companion object {
        val SECRET_TAGS = arrayOf("password", "passwd", "otp", "cvv", "cvc", "card", "pin")
    }

    private fun kindOf(c: SemanticsConfiguration, n: SemanticsNode): String {
        if (c.contains(SemanticsProperties.EditableText) || c.contains(SemanticsProperties.Password)) return Kind.INPUT
        val role = c.getOrNull(SemanticsProperties.Role)
        when (role) {
            Role.Switch, Role.Checkbox, Role.RadioButton -> return Kind.SWITCH
            Role.Button, Role.Tab, Role.DropdownList -> return Kind.BUTTON
            Role.Image -> return Kind.IMAGE
        }
        if (c.contains(SemanticsProperties.ToggleableState)) return Kind.SWITCH
        if (c.contains(SemanticsProperties.VerticalScrollAxisRange) ||
            c.contains(SemanticsProperties.HorizontalScrollAxisRange) ||
            c.contains(SemanticsProperties.CollectionInfo)
        ) return Kind.LIST
        if (c.contains(SemanticsActions.OnClick)) return Kind.BUTTON
        if (c.contains(SemanticsProperties.Text)) return Kind.TEXT
        if (c.contains(SemanticsProperties.ContentDescription) && n.children.isEmpty()) return Kind.IMAGE
        return Kind.VIEW
    }
}
