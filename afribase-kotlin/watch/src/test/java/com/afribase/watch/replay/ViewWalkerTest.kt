package com.afribase.watch.replay

import android.app.Activity
import android.graphics.Color
import android.os.Looper
import android.text.InputType
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowManager
import android.webkit.WebView
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView
import com.afribase.watch.watchBlock
import com.afribase.watch.watchSecureScreen
import com.afribase.watch.watchUnmask
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ViewWalkerTest {
    private fun activity(build: (Activity) -> View): Activity {
        val a = Robolectric.buildActivity(Activity::class.java).setup().visible().get()
        a.setContentView(build(a))
        shadowOf(Looper.getMainLooper()).idle()
        return a
    }

    private fun walk(a: Activity, maskAllText: Boolean = true, ids: NodeIds = NodeIds(), flags: Int = a.window.attributes.flags): Pair<WalkResult, WalkContext> {
        val decor = a.window.decorView
        val ctx = WalkContext(
            density = a.resources.displayMetrics.density,
            screenWpx = decor.width,
            screenHpx = decor.height,
            maskAllText = maskAllText,
            ids = ids,
            deadlineNanos = Long.MAX_VALUE,
        )
        return walker().walk("Main", decor, flags, IntArray(2), ctx) to ctx
    }

    private fun walker() = ViewWalker(null)

    private fun all(n: WireNode?): List<WireNode> = if (n == null) emptyList() else listOf(n) + (n.children ?: emptyList<WireNode>()).flatMap { all(it) }

    private fun form(a: Activity): View = LinearLayout(a).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(Color.WHITE)
        addView(TextView(a).apply { text = "Jane Doe"; setTextColor(Color.BLACK) })
        addView(TextView(a).apply { text = "Checkout" }.watchUnmask())
        addView(EditText(a).apply { setText("jane@example.com") }.watchUnmask())
        addView(EditText(a).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText("hunter2")
        })
        addView(Button(a).apply { text = "Pay" })
        addView(Switch(a).apply { text = "Alerts" }, LinearLayout.LayoutParams(MATCH_PARENT, 30))
        addView(FrameLayout(a).apply {
            setBackgroundColor(Color.RED)
            addView(TextView(a).apply { text = "4242 4242 4242 4242" })
        }.watchBlock(), LinearLayout.LayoutParams(MATCH_PARENT, 30))
// Robolectric's WebView always measures 0x0, so it is skipped here; kind checked below.
        addView(WebView(a), LinearLayout.LayoutParams(MATCH_PARENT, 30))
        addView(TextView(a).apply { text = "hidden"; visibility = View.GONE })
        addView(TextView(a).apply { text = "invisible"; alpha = 0f })
    }

    @Test
    fun treeToNodesWithMasking() {
        val a = activity(::form)
        val (r, _) = walk(a)
        assertFalse(r.secure)
        assertNotNull(r.root)
        val nodes = all(r.root)
        val texts = nodes.filter { it.k == Kind.TEXT }
        // (A further text node is the default theme's action bar title, masked too.)
        assertEquals(listOf("********", "Checkout"), texts.take(2).map { it.text })
        assertEquals("#000000", texts[0].fg)

        val inputs = nodes.filter { it.k == Kind.INPUT }
        assertEquals(2, inputs.size)
        // Inputs always masked, even under watchUnmask.
        assertEquals("****************", inputs[0].text)
        // Password: no text, no length.
        assertTrue(inputs[1].textNull)
        assertNull(inputs[1].text)
        assertTrue(r.root!!.toJson().contains("\"k\":\"input\"") && r.root!!.toJson().contains("\"text\":null"))

        assertEquals("***", nodes.single { it.k == Kind.BUTTON }.text)
        assertEquals(1, nodes.count { it.k == Kind.SWITCH })

        val blocked = nodes.single { it.k == Kind.BLOCKED }
        assertNull(blocked.children)
        assertNull(blocked.text)
        assertEquals(Kind.WEB, ViewWalker.kindOf(WebView(a)))

        // Hidden and transparent views skipped; no raw text anywhere.
        val json = r.root!!.toJson()
        assertFalse(json.contains("hidden"))
        assertFalse(json.contains("invisible"))
        assertFalse(json.contains("4242"))
        assertFalse(json.contains("hunter2"))
        assertFalse(json.contains("jane"))
        assertFalse(json.contains("Jane"))
    }

    @Test
    fun maskAllTextOffSendsLabelsButNotInputs() {
        val a = activity(::form)
        val nodes = all(walk(a, maskAllText = false).first.root)
        assertEquals("Jane Doe", nodes.first { it.k == Kind.TEXT }.text)
        assertEquals("Pay", nodes.single { it.k == Kind.BUTTON }.text)
        assertEquals("****************", nodes.first { it.k == Kind.INPUT }.text)
    }

    @Test
    fun flagSecureSendsNoTree() {
        val a = activity(::form)
        a.window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        val (r, _) = walk(a)
        assertTrue(r.secure)
        assertNull(r.root)
        val json = WireframeRecorder.snapshotJson(5, r)
        assertTrue(json, json.contains("\"secure\":true"))
        assertTrue(json, json.endsWith("\"root\":null}"))
    }

    @Test
    fun secureScreenMarkerAnywhereSendsNoTree() {
        val a = activity { act ->
            LinearLayout(act).apply {
                addView(TextView(act).apply { text = "a" })
                addView(LinearLayout(act).apply { addView(TextView(act).apply { text = "b" }.watchSecureScreen()) })
            }
        }
        val (r, _) = walk(a)
        assertTrue(r.secure)
        assertNull(r.root)
    }

    @Test
    fun xmlTagMarkersWork() {
        val a = activity { act ->
            LinearLayout(act).apply {
                addView(TextView(act).apply { text = "secret"; tag = "watchBlock" })
            }
        }
        assertEquals(1, all(walk(a).first.root).count { it.k == Kind.BLOCKED })
    }

    @Test
    fun idsStableAndHashChangesOnlyWithTree() {
        val ids = NodeIds()
        var label: TextView? = null
        val a = activity { act -> LinearLayout(act).apply { addView(TextView(act).apply { text = "one"; label = this }) } }
        val (r1, _) = walk(a, ids = ids)
        val (r2, _) = walk(a, ids = ids)
        assertEquals(r1.hash, r2.hash)
        assertEquals(all(r1.root).map { it.id }, all(r2.root).map { it.id })
        label!!.text = "three"
        shadowOf(Looper.getMainLooper()).idle()
        val (r3, _) = walk(a, ids = ids)
        assertTrue(r1.hash != r3.hash)
        assertEquals(all(r1.root).last().id, all(r3.root).last().id)
    }

    @Test
    fun capsNodesAndSetsTruncated() {
        val a = activity { act ->
            LinearLayout(act).apply {
                orientation = LinearLayout.VERTICAL
                repeat(50) {
                    addView(LinearLayout(act).apply {
                        repeat(70) { addView(View(act).apply { setBackgroundColor(Color.BLUE) }, LinearLayout.LayoutParams(2, 2)) }
                    })
                }
            }
        }
        val (r, ctx) = walk(a)
        assertTrue(r.truncated)
        assertTrue(ctx.nodes <= WalkContext.MAX_NODES)
        assertTrue(WireframeRecorder.snapshotJson(1, r).contains("\"truncated\":true"))
    }

    @Test
    fun capsDepth() {
        val a = activity { act ->
            var inner: FrameLayout = FrameLayout(act)
            val root = inner
            repeat(100) {
                val next = FrameLayout(act).apply { setBackgroundColor(Color.GRAY) }
                inner.addView(next)
                inner = next
            }
            root
        }
        fun depth(n: WireNode?): Int = if (n == null) 0 else 1 + (n.children?.maxOfOrNull { depth(it) } ?: 0)
        assertTrue(depth(walk(a).first.root) <= WalkContext.MAX_DEPTH + 1)
    }

    @Test
    fun coordinatesAreDpRelativeToScreen() {
        val a = activity { act ->
            FrameLayout(act).apply {
                addView(View(act).apply { setBackgroundColor(Color.GREEN); translationX = 0f }, FrameLayout.LayoutParams(200, 100).apply { leftMargin = 50; topMargin = 30 })
            }
        }
        val d = a.resources.displayMetrics.density
        val box = all(walk(a).first.root).single { it.bg == "#00FF00" }
        assertEquals(200 / d, box.w, 0.01f)
        assertEquals(100 / d, box.h, 0.01f)
        assertTrue(box.x >= 50 / d - 0.01f)
    }
}
