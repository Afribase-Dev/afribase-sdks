package com.afribase.watch

/**
 * A tiny JSON writer, so the SDK needs no JSON library and its output is the
 * same on the JVM (unit tests) and on a device (android's org.json is a stub
 * in JVM tests).
 *
 * Values: null, String, Boolean, Number, Map<String, *>, List<*>, Array<*>,
 * [RawJson] (already-rendered JSON). Anything else becomes its toString().
 * Map entries whose value is null are skipped; use [JsonNull] to write null.
 */
internal object Json {
    fun write(value: Any?): String {
        val sb = StringBuilder(256)
        write(sb, value)
        return sb.toString()
    }

    fun write(sb: StringBuilder, value: Any?) {
        when (value) {
            null, JsonNull -> sb.append("null")
            is RawJson -> sb.append(value.json)
            is String -> string(sb, value)
            is Boolean -> sb.append(if (value) "true" else "false")
            is Float -> number(sb, value.toDouble())
            is Double -> number(sb, value)
            is Number -> sb.append(value.toLong())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                for ((k, v) in value) {
                    if (v == null) continue
                    if (!first) sb.append(',')
                    first = false
                    string(sb, k.toString())
                    sb.append(':')
                    write(sb, v)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                var first = true
                for (v in value) {
                    if (!first) sb.append(',')
                    first = false
                    write(sb, v)
                }
                sb.append(']')
            }
            is Array<*> -> write(sb, value.asList())
            else -> string(sb, value.toString())
        }
    }

    /** Integers without a fraction, others with at most 2 decimals. */
    fun number(sb: StringBuilder, d: Double) {
        if (d.isNaN() || d.isInfinite()) {
            sb.append('0')
            return
        }
        val r = Math.round(d * 100.0) / 100.0
        if (r == Math.rint(r) && Math.abs(r) < 1e15) sb.append(r.toLong()) else sb.append(r)
    }

    fun string(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ' || c == ' ' || c == ' ') {
                    sb.append(String.format("\\u%04x", c.code))
                } else {
                    sb.append(c)
                }
            }
        }
        sb.append('"')
    }
}

/** Already-rendered JSON, written as is. */
internal class RawJson(val json: String) {
    override fun toString(): String = json
}

/** Writes an explicit null inside a map (null values are otherwise skipped). */
internal object JsonNull
