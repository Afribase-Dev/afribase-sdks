package com.afribase.watch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors "Watch live presence" in sdks/afribase-js/test/watch-replay.test.ts. */
class PresenceTest {
    private val sched = FakeScheduler()
    private val bodies = ArrayList<String>()
    private val transport = object : Transport {
        override fun post(url: String, body: ByteArray, key: String): Int {
            assertEquals("https://api.test/watch/ingest/presence?key=abw_test", url)
            bodies.add(String(body))
            return 204
        }
    }
    private val presence = Presence(
        Urls.sub("https://api.test/watch/ingest", "presence", "abw_test"), "abw_test", "1.0",
        { "sid" }, { null }, transport, sched, now = { sched.now }, title = { "Checkout" },
    )

    @Test
    fun heartbeatAtStartAndEvery15sWhileForeground() {
        presence.screen("Home")
        presence.foreground()
        sched.runDue()
        assertEquals(1, bodies.size)
        assertTrue(bodies[0], bodies[0].contains("\"path\":\"app://Home\""))
        assertTrue(bodies[0].contains("\"title\":\"Checkout\""))
        assertTrue(bodies[0].contains("\"leaving\":false"))
        sched.advance(15_000)
        assertEquals(2, bodies.size)
        sched.advance(30_000)
        assertEquals(4, bodies.size)
    }

    @Test
    fun pausesInTheBackgroundAndSaysLeaving() {
        presence.foreground()
        sched.runDue()
        presence.background()
        sched.runDue()
        assertEquals(2, bodies.size)
        assertTrue(bodies[1].contains("\"leaving\":true"))
        sched.advance(60_000)
        assertEquals(2, bodies.size)
        presence.foreground()
        sched.advance(2_000)
        assertEquals(3, bodies.size)
    }

    @Test
    fun sendsOnScreenChangeWithLastActions() {
        presence.foreground()
        sched.advance(3_000)
        repeat(4) { presence.addAction("click", "MaterialButton 'Tell your story'") }
        presence.screen("PersonalManager")
        sched.runDue()
        assertEquals(2, bodies.size)
        val b = bodies.last()
        assertTrue(b, b.contains("\"path\":\"app://PersonalManager\""))
        assertEquals(4, Regex("\"type\":\"click\"").findAll(b).count())
        assertTrue(b.contains("\"type\":\"navigation\",\"label\":\"PersonalManager\""))
    }

    @Test
    fun onePer2sOnQuickScreenChanges() {
        presence.foreground()
        sched.runDue()
        presence.screen("A")
        presence.screen("B")
        sched.runDue()
        assertEquals(1, bodies.size)
        sched.advance(2_000)
        assertEquals(2, bodies.size)
        assertTrue(bodies[1].contains("app://B"))
    }

    @Test
    fun stopEndsHeartbeats() {
        presence.foreground()
        sched.runDue()
        presence.stop()
        sched.runDue()
        val n = bodies.size
        sched.advance(60_000)
        assertEquals(n, bodies.size)
    }

    @Test
    fun labelsAndTitles() {
        assertEquals("button 'Pay'", ViewFinder.label(mapOf("tag" to "button", "text" to "Pay")))
        assertEquals("button#pay", ViewFinder.label(mapOf("tag" to "button", "id" to "pay")))
        assertEquals("Order ****** for ***", Presence.maskTitle("Order 123456 for ada@example.com"))
        assertFalse(Presence.maskTitle("a@b.co").contains("@"))
    }
}
