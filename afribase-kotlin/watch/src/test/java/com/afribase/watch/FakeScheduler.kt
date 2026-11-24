package com.afribase.watch

import java.util.concurrent.AbstractExecutorService
import java.util.concurrent.Callable
import java.util.concurrent.Delayed
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/** A ScheduledExecutorService on a fake clock: nothing runs until [advance]. */
class FakeScheduler : AbstractExecutorService(), ScheduledExecutorService {
    var now = 1_000_000L
    private var seq = 0L

    inner class Task(var at: Long, val period: Long, val block: () -> Unit) : ScheduledFuture<Any?> {
        val id = seq++
        var cancelled = false
        override fun cancel(mayInterruptIfRunning: Boolean): Boolean { cancelled = true; return true }
        override fun isCancelled() = cancelled
        override fun isDone() = cancelled
        override fun get(): Any? = null
        override fun get(timeout: Long, unit: TimeUnit): Any? = null
        override fun getDelay(unit: TimeUnit) = unit.convert(at - now, TimeUnit.MILLISECONDS)
        override fun compareTo(other: Delayed) = getDelay(TimeUnit.MILLISECONDS).compareTo(other.getDelay(TimeUnit.MILLISECONDS))
    }

    private val tasks = ArrayList<Task>()

    /** Runs everything due up to now + ms, in time order. */
    fun advance(ms: Long) {
        val end = now + ms
        while (true) {
            val t = tasks.filter { !it.cancelled && it.at <= end }.minWithOrNull(compareBy({ it.at }, { it.id })) ?: break
            now = t.at
            if (t.period > 0) t.at += t.period else tasks.remove(t)
            t.block()
        }
        now = end
    }

    fun runDue() = advance(0)

    override fun execute(command: Runnable) { tasks.add(Task(now, 0) { command.run() }) }
    override fun schedule(command: Runnable, delay: Long, unit: TimeUnit): ScheduledFuture<*> =
        Task(now + unit.toMillis(delay), 0) { command.run() }.also { tasks.add(it) }
    override fun <V : Any?> schedule(callable: Callable<V>, delay: Long, unit: TimeUnit): ScheduledFuture<V> =
        throw UnsupportedOperationException()
    override fun scheduleAtFixedRate(command: Runnable, initialDelay: Long, period: Long, unit: TimeUnit): ScheduledFuture<*> =
        Task(now + unit.toMillis(initialDelay), unit.toMillis(period)) { command.run() }.also { tasks.add(it) }
    override fun scheduleWithFixedDelay(command: Runnable, initialDelay: Long, delay: Long, unit: TimeUnit): ScheduledFuture<*> =
        scheduleAtFixedRate(command, initialDelay, delay, unit)
    override fun shutdown() {}
    override fun shutdownNow(): MutableList<Runnable> = mutableListOf()
    override fun isShutdown() = false
    override fun isTerminated() = false
    override fun awaitTermination(timeout: Long, unit: TimeUnit) = true
}
