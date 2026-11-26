package com.afribase.watch.replay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MaskingTest {
    @Test
    fun masksKeepingLengthCappedAt40() {
        assertEquals("*****", Masking.mask("hello"))
        assertEquals(40, Masking.mask("x".repeat(100))!!.length)
        assertEquals("", Masking.mask(""))
        assertNull(Masking.mask(null))
    }

    @Test
    fun textRules() {
        // Default (maskAllText and maskAllInputs off): labels and inputs as shown.
        assertEquals("Jane", Masking.textFor("Jane", isInput = false, isSecret = false, unmasked = false, maskAllText = false))
        assertEquals("jane@x.io", Masking.textFor("jane@x.io", isInput = true, isSecret = false, unmasked = false, maskAllText = false))
        assertEquals(40, (Masking.textFor("y".repeat(99), false, false, false, false) as String).length)
        // Secrets: never text or length, whatever the options and markers.
        assertTrue(Masking.textFor("hunter2", true, isSecret = true, unmasked = true, maskAllText = false) === Masking.SECRET)
        assertTrue(Masking.textFor("hunter2", true, true, false, false, maskAllInputs = false, masked = false) === Masking.SECRET)
        // watchMask: that view masked even with every option off.
        assertEquals("****", Masking.textFor("Jane", false, false, false, false, masked = true))
        assertEquals("****", Masking.textFor("Jane", true, false, true, false, masked = true))
        // maskAllInputs opt-in: inputs masked, labels not.
        assertEquals("****", Masking.textFor("Jane", isInput = true, isSecret = false, unmasked = true, maskAllText = false, maskAllInputs = true))
        assertEquals("Jane", Masking.textFor("Jane", isInput = false, isSecret = false, unmasked = false, maskAllText = false, maskAllInputs = true))
        // maskAllText opt-in: everything masked, watchUnmask labels excepted, inputs always.
        assertEquals("****", Masking.textFor("Jane", false, false, unmasked = false, maskAllText = true))
        assertEquals("Jane", Masking.textFor("Jane", false, false, unmasked = true, maskAllText = true))
        assertEquals("****", Masking.textFor("Jane", isInput = true, isSecret = false, unmasked = true, maskAllText = true))
    }

    @Test
    fun secretRendersAsJsonNull() {
        val n = WireNode(1, Kind.INPUT, 0f, 0f, 10f, 10f)
        Masking.apply(n, Masking.SECRET)
        assertEquals("{\"id\":1,\"k\":\"input\",\"x\":0,\"y\":0,\"w\":10,\"h\":10,\"text\":null}", n.toJson())
    }
}

class WireNodeTest {
    @Test
    fun rendersContractNode() {
        val root = WireNode(1, Kind.VIEW, 0f, 0f, 412f, 915f).apply { bg = "#FFFFFF" }
        val child = WireNode(17, Kind.BUTTON, 16f, 80.5f, 380f, 56f).apply {
            fg = "#111111"; r = 12f; a = 0.5f; text = "*****"
        }
        root.add(child)
        assertEquals(
            "{\"id\":1,\"k\":\"view\",\"x\":0,\"y\":0,\"w\":412,\"h\":915,\"bg\":\"#FFFFFF\",\"c\":[" +
                "{\"id\":17,\"k\":\"button\",\"x\":16,\"y\":80.5,\"w\":380,\"h\":56,\"bg\":null".replace(",\"bg\":null", "") +
                ",\"fg\":\"#111111\",\"r\":12,\"a\":0.5,\"text\":\"*****\"}]}",
            root.toJson(),
        )
    }

    @Test
    fun hashChangesWithGeometryAndText() {
        val a = WireNode(1, Kind.TEXT, 0f, 0f, 10f, 10f).apply { text = "**" }
        val b = WireNode(1, Kind.TEXT, 0f, 0f, 10f, 11f).apply { text = "**" }
        val c = WireNode(1, Kind.TEXT, 0f, 0f, 10f, 10f).apply { text = "***" }
        val d = WireNode(1, Kind.TEXT, 0f, 0f, 10f, 10f).apply { text = "**" }
        assertTrue(a.hash() != b.hash())
        assertTrue(a.hash() != c.hash())
        assertEquals(a.hash(), d.hash())
    }

    @Test
    fun hoistsBareContainers() {
        val parent = WireNode(1, Kind.VIEW, 0f, 0f, 100f, 100f)
        val wrapper = WireNode(2, Kind.VIEW, 0f, 0f, 100f, 100f).apply { add(WireNode(3, Kind.TEXT, 0f, 0f, 10f, 10f)) }
        ViewWalker.hoistInto(parent, wrapper)
        assertEquals(listOf(3), parent.children!!.map { it.id })
        val card = WireNode(4, Kind.VIEW, 0f, 0f, 100f, 100f).apply { bg = "#FF0000"; add(WireNode(5, Kind.TEXT, 0f, 0f, 1f, 1f)) }
        ViewWalker.hoistInto(parent, card)
        assertEquals(listOf(3, 4), parent.children!!.map { it.id })
    }
}

class ReplayBufferTest {
    private fun ev(t: Long, type: String = "touch") = BufferedEvent(t, type, "{\"t\":$t,\"type\":\"$type\"}")

    @Test
    fun dropsEventsBeforeFirstSnapshot() {
        val b = ReplayBuffer()
        b.add(ev(0))
        b.add(ev(1, "screen"))
        assertEquals(0, b.size())
        b.add(ev(2, "snapshot"))
        b.add(ev(3))
        assertEquals(listOf("snapshot", "touch"), b.events(3).map { it.type })
    }

    @Test
    fun keepsLast60sStartingAtASnapshot() {
        val b = ReplayBuffer()
        b.add(ev(0, "snapshot"))
        b.add(ev(5_000))
        b.add(ev(10_000, "snapshot"))
        b.add(ev(20_000, "snapshot"))
        b.add(ev(65_000))
        // Window start 5_000: the snapshot at 0 is the newest one at or before it.
        assertEquals(0L, b.events(65_000).first().t)
        // Window start 15_000: snapshot at 10_000 opens the buffer.
        val at75 = b.events(75_000)
        assertEquals(10_000L, at75.first().t)
        assertEquals("snapshot", at75.first().type)
        // Window start 30_000: snapshot at 20_000.
        assertEquals(20_000L, b.events(90_000).first().t)
    }

    @Test
    fun alwaysStartsWithSnapshotEvenWhenStale() {
        val b = ReplayBuffer()
        b.add(ev(0, "snapshot"))
        b.add(ev(1_000))
        // Nothing newer: the old snapshot stays so the next events can be drawn.
        val e = b.events(500_000)
        assertEquals("snapshot", e.first().type)
    }

    @Test
    fun capsEventCountAtASnapshotBoundary() {
        val b = ReplayBuffer(maxEvents = 10)
        b.add(ev(0, "snapshot"))
        repeat(5) { b.add(ev(1L + it)) }
        b.add(ev(10, "snapshot"))
        repeat(6) { b.add(ev(11L + it)) }
        val e = b.events(20)
        assertTrue(e.size <= 10)
        assertEquals(10L, e.first().t)
        assertEquals("snapshot", e.first().type)
    }

    @Test
    fun snapshotPolicyEmitsOnChangeOrKeyframe() {
        val p = SnapshotPolicy()
        assertTrue(p.shouldEmit(1, "A", 0))
        assertFalse(p.shouldEmit(1, "A", 500))
        assertTrue(p.shouldEmit(2, "A", 1_000))
        assertFalse(p.shouldEmit(2, "A", 9_000))
        assertTrue(p.shouldEmit(2, "A", 11_000)) // keyframe
        assertTrue(p.shouldEmit(2, "B", 11_500)) // new screen
    }

    @Test
    fun uploadGateLimits() {
        val g = UploadGate()
        assertTrue(g.tryTrigger(1_000))
        // Pending upload: no second one.
        assertFalse(g.tryTrigger(1_100))
        g.done()
        // Within 30 s of the last.
        assertFalse(g.tryTrigger(20_000))
        assertTrue(g.tryTrigger(31_000))
        g.done()
        var t = 31_000L
        repeat(20) {
            t += 31_000
            if (g.tryTrigger(t)) g.done()
        }
        assertEquals(UploadGate.MAX_PER_LAUNCH, g.count())
    }

    @Test
    fun payloadHasContractFields() {
        val meta = ReplayMeta(
            "abw_1", "sid", null, "1.0", "prod", "CheckoutActivity",
            linkedMapOf("os" to "Android 15", "model" to "Pixel 8", "w" to 412, "h" to 915, "density" to 2.625f), "error",
        )
        val body = ReplayPayload.build(meta, listOf(ev(100, "snapshot"), ev(200)))
        assertEquals(
            "{\"key\":\"abw_1\",\"sessionId\":\"sid\",\"release\":\"1.0\",\"environment\":\"prod\",\"format\":\"wireframe\"," +
                "\"platform\":\"android\",\"url\":\"app://CheckoutActivity\",\"device\":{\"os\":\"Android 15\",\"model\":\"Pixel 8\"," +
                "\"w\":412,\"h\":915,\"density\":2.63},\"trigger\":\"error\",\"startedAt\":100,\"endedAt\":200,\"events\":[" +
                "{\"t\":100,\"type\":\"snapshot\"},{\"t\":200,\"type\":\"touch\"}]}",
            body,
        )
    }

    @Test
    fun halveStartsAtASnapshot() {
        val events = listOf(ev(0, "snapshot"), ev(1), ev(2), ev(3, "snapshot"), ev(4), ev(5))
        val h = ReplayPayload.halve(events)
        assertNotNull(h)
        assertEquals(3L, h!!.first().t)
        assertNull(ReplayPayload.halve(listOf(ev(0, "snapshot"), ev(1))))
    }
}
