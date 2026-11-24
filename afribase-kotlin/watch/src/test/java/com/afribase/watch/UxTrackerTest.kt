package com.afribase.watch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors the "Watch UX signals" cases of sdks/afribase-js/test/watch.test.ts. */
class UxTrackerTest {
    private var clock = 1_000_000L
    private val timers = ArrayList<Pair<Long, () -> Unit>>()
    private val sent = ArrayList<Pair<String, Map<String, Any?>>>()
    private val ux = UxTracker(emit = { t, d -> sent.add(t to d) }, now = { clock }, schedule = { delay, block -> timers.add(clock + delay to block) })

    private fun advance(ms: Long) {
        val end = clock + ms
        while (true) {
            val next = timers.filter { it.first <= end }.minByOrNull { it.first } ?: break
            timers.remove(next)
            clock = next.first
            next.second()
        }
        clock = end
    }

    private fun of(type: String) = sent.filter { it.first == type }.map { it.second }
    private fun el(id: String) = mapOf<String, Any?>("tag" to "Button", "kind" to "button", "id" to id)

    private fun tap(id: String, times: Int = 1, tappable: Boolean = true, form: String? = "Checkout") {
        repeat(times) {
            ux.tap(el(id), tappable, form)
            advance(100)
        }
    }

    @Test
    fun rageClickOncePerBurstWithTheElement() {
        tap("pay", 4)
        advance(1500)
        val rage = of("rage_click")
        assertEquals(1, rage.size)
        assertEquals(el("pay"), rage[0]["element"])
        assertEquals(0, of("dead_click").size) // the burst is the signal
    }

    @Test
    fun rageAgainAfterAPause() {
        tap("pay", 3)
        advance(2000)
        tap("pay", 3)
        assertEquals(2, of("rage_click").size)
    }

    @Test
    fun deadClickOnlyWhenNothingReacts() {
        tap("dead")
        advance(1500)
        // Same element again within 5 s: not reported twice.
        tap("dead")
        advance(1500)
        tap("live")
        ux.activity() // layout changed
        advance(1500)
        tap("req")
        ux.request()
        advance(1500)
        tap("plain", tappable = false)
        advance(1500)
        val dead = of("dead_click")
        assertEquals(1, dead.size)
        assertEquals(el("dead"), dead[0]["element"])
    }

    @Test
    fun abandonedFormReportsLastFieldNotASubmittedOne() {
        ux.field("Signup", "email", "email")
        ux.field("Signup", "phone", "tel")
        ux.field("Search", "q", "text")
        ux.submitted("Search")
        ux.beforeLeave()
        val ab = of("form_abandon")
        assertEquals(1, ab.size)
        assertEquals(mapOf("form" to "Signup", "field" to "phone", "fieldType" to "tel"), ab[0])
    }

    @Test
    fun navigationLeavesTheFormUnlessATapPostedIt() {
        ux.navigation("Editor")
        ux.field("Editor", "title", "text")
        tap("save", form = "Editor")
        ux.request()
        ux.navigation("Next")
        assertEquals(0, of("form_abandon").size)
        ux.navigation("Editor")
        ux.field("Editor", "title", "text")
        ux.navigation("Other")
        assertEquals(1, of("form_abandon").size)
    }

    @Test
    fun errorRightAfterAClick() {
        tap("buy")
        ux.error("payment failed")
        val ea = of("error_after_action")
        assertEquals(1, ea.size)
        assertEquals(el("buy"), ea[0]["element"])
        advance(3000)
        ux.error("later")
        assertEquals(1, of("error_after_action").size)
    }

    @Test
    fun navigationLoop() {
        for (p in listOf("Cart", "Checkout", "Cart", "Checkout")) {
            ux.navigation(p)
            advance(1000)
        }
        val loop = of("nav_loop")
        assertEquals(1, loop.size)
        assertEquals(listOf("Cart", "Checkout"), loop[0]["paths"])
    }

    @Test
    fun slowInteractions() {
        ux.interaction(el("filter"), "tap", 120)
        ux.interaction(el("filter"), "tap", 840)
        ux.interaction(el("filter"), "tap", 900) // same element within 10 s
        val slow = of("slow_interaction")
        assertEquals(1, slow.size)
        assertEquals(mapOf("element" to el("filter"), "eventType" to "tap", "durationMs" to 840L), slow[0])
    }

    @Test
    fun capsAtFifty() {
        repeat(100) { i ->
            tap("b$i", 3)
            advance(2000)
        }
        assertEquals(UxTracker.MAX_UX, sent.size)
    }

    @Test
    fun messagesLikeJs() {
        assertEquals("rage_click on Button#pay", UxTracker.message("rage_click", mapOf("element" to el("pay"))))
        assertTrue(UxTracker.message("nav_loop", mapOf("paths" to listOf("A", "B"))) == "nav_loop")
    }
}
