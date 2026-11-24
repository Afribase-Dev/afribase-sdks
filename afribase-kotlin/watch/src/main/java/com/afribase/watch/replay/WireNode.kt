package com.afribase.watch.replay

/** Node kinds of the wireframe contract. */
internal object Kind {
    const val VIEW = "view"
    const val TEXT = "text"
    const val IMAGE = "image"
    const val BUTTON = "button"
    const val INPUT = "input"
    const val SWITCH = "switch"
    const val LIST = "list"
    const val WEB = "web"
    const val BLOCKED = "blocked"
}

/**
 * One node of a wireframe snapshot (see watch-wireframe-contract.md, Node).
 * Built on the main thread by a walker, rendered to JSON off it, never
 * changed after the walk.
 *
 * [text] is already masked. [textNull] means a secure field: `"text": null`.
 */
internal class WireNode(
    val id: Int,
    val k: String,
    val x: Float,
    val y: Float,
    val w: Float,
    val h: Float,
) {
    var bg: String? = null
    var fg: String? = null
    var r: Float = 0f
    var a: Float = 1f
    var text: String? = null
    var textNull: Boolean = false
    var children: MutableList<WireNode>? = null

    fun add(child: WireNode) {
        val c = children ?: ArrayList<WireNode>(4).also { children = it }
        c.add(child)
    }

    fun render(sb: StringBuilder) {
        sb.append("{\"id\":").append(id)
        sb.append(",\"k\":\"").append(k).append('"')
        sb.append(",\"x\":"); com.afribase.watch.Json.number(sb, x.toDouble())
        sb.append(",\"y\":"); com.afribase.watch.Json.number(sb, y.toDouble())
        sb.append(",\"w\":"); com.afribase.watch.Json.number(sb, w.toDouble())
        sb.append(",\"h\":"); com.afribase.watch.Json.number(sb, h.toDouble())
        bg?.let { sb.append(",\"bg\":\"").append(it).append('"') }
        fg?.let { sb.append(",\"fg\":\"").append(it).append('"') }
        if (r > 0f) { sb.append(",\"r\":"); com.afribase.watch.Json.number(sb, r.toDouble()) }
        if (a < 1f) { sb.append(",\"a\":"); com.afribase.watch.Json.number(sb, a.toDouble()) }
        if (textNull) {
            sb.append(",\"text\":null")
        } else {
            text?.let { sb.append(",\"text\":"); com.afribase.watch.Json.string(sb, it) }
        }
        val c = children
        if (!c.isNullOrEmpty()) {
            sb.append(",\"c\":[")
            for (i in c.indices) {
                if (i > 0) sb.append(',')
                c[i].render(sb)
            }
            sb.append(']')
        }
        sb.append('}')
    }

    fun toJson(): String = StringBuilder(128).also { render(it) }.toString()

    /** Cheap structural hash, folded into the walk's tree hash. */
    fun hash(): Int {
        var v = id
        v = 31 * v + k.hashCode()
        v = 31 * v + x.toRawBits()
        v = 31 * v + y.toRawBits()
        v = 31 * v + w.toRawBits()
        v = 31 * v + h.toRawBits()
        v = 31 * v + (bg?.hashCode() ?: 0)
        v = 31 * v + (fg?.hashCode() ?: 0)
        v = 31 * v + r.toRawBits()
        v = 31 * v + a.toRawBits()
        v = 31 * v + (text?.hashCode() ?: 0)
        v = 31 * v + if (textNull) 1 else 0
        return v
    }
}

/** The result of one walk of a screen. */
internal class WalkResult(
    val screen: String,
    val w: Float,
    val h: Float,
    val secure: Boolean,
    val root: WireNode?,
    val truncated: Boolean,
    val hash: Int,
    val nodes: Int,
)

/** Text masking rules shared by every walker. */
internal object Masking {
    const val MAX_TEXT = 40

    /** Each character becomes `*`, length kept, capped at 40. */
    fun mask(s: CharSequence?): String? {
        if (s == null) return null
        val n = minOf(s.length, MAX_TEXT)
        if (n == 0) return ""
        val sb = StringBuilder(n)
        repeat(n) { sb.append('*') }
        return sb.toString()
    }

    /** Real text, capped at 40 characters. */
    fun cap(s: CharSequence?): String? {
        if (s == null) return null
        return if (s.length > MAX_TEXT) s.subSequence(0, MAX_TEXT).toString() else s.toString()
    }

    /**
     * The text a node carries.
     * @param isInput an editable field: always masked.
     * @param isSecret password / one-time-code / card field: never sent ([SECRET]).
     * @param unmasked the view or an ancestor carries `watchUnmask`.
     * @param maskAllText the app's maskAllText setting.
     */
    fun textFor(raw: CharSequence?, isInput: Boolean, isSecret: Boolean, unmasked: Boolean, maskAllText: Boolean): Any? {
        if (isSecret) return SECRET
        if (raw == null) return null
        if (isInput) return mask(raw)
        return if (unmasked || !maskAllText) cap(raw) else mask(raw)
    }

    /** Marker for `"text": null`. */
    val SECRET = Any()

    fun apply(node: WireNode, text: Any?) {
        if (text === SECRET) node.textNull = true else node.text = text as String?
    }
}
