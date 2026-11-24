package com.afribase.watch

import java.io.File
import java.util.concurrent.atomic.AtomicLong

/**
 * Events waiting to be sent, one file each, so they survive the process
 * dying (a crash is written here synchronously and sent on the next launch).
 * Oldest files are dropped past [maxFiles].
 */
internal class EventStore(private val dir: File, private val maxFiles: Int, private val suffix: String) {
    private val seq = AtomicLong(0)

    init {
        try {
            dir.mkdirs()
        } catch (_: Throwable) {
        }
    }

    /** Writes the bytes; safe to call from any thread, including a crashing one. */
    fun save(bytes: ByteArray): File? = try {
        val name = String.format("%013d-%06d%s", System.currentTimeMillis(), seq.incrementAndGet() % 1_000_000, suffix)
        val tmp = File(dir, "$name.tmp")
        tmp.writeBytes(bytes)
        val f = File(dir, name)
        if (!tmp.renameTo(f)) {
            tmp.delete()
            null
        } else {
            trim()
            f
        }
    } catch (_: Throwable) {
        null
    }

    /** Pending files, oldest first. */
    fun list(): List<File> = try {
        (dir.listFiles { f -> f.isFile && f.name.endsWith(suffix) } ?: emptyArray()).sortedBy { it.name }
    } catch (_: Throwable) {
        emptyList()
    }

    fun read(f: File): ByteArray? = try {
        f.readBytes()
    } catch (_: Throwable) {
        null
    }

    fun delete(f: File) {
        try {
            f.delete()
        } catch (_: Throwable) {
        }
    }

    private fun trim() {
        val files = list()
        if (files.size > maxFiles) files.take(files.size - maxFiles).forEach { delete(it) }
        // Stale temp files from a write cut short.
        try {
            dir.listFiles { f -> f.name.endsWith(".tmp") && System.currentTimeMillis() - f.lastModified() > 60_000 }?.forEach { it.delete() }
        } catch (_: Throwable) {
        }
    }
}
