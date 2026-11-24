package com.afribase.watch.sample

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import com.afribase.watch.AfribaseWatch
import com.afribase.watch.watchBlock
import com.afribase.watch.watchUnmask

/** A plain View screen: label, inputs, a blocked card and buttons that make errors. */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(Color.WHITE)
        }
        root.addView(TextView(this).apply { text = "Checkout"; textSize = 24f }.watchUnmask())
        root.addView(TextView(this).apply { text = "Masked: Jane Doe, 12 Main St" })
        root.addView(EditText(this).apply { hint = "Email"; setText("jane@example.com") })
        root.addView(EditText(this).apply {
            hint = "Password"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText("hunter2")
        })
        root.addView(LinearLayout(this).apply {
            setBackgroundColor(Color.parseColor("#FFEEDD"))
            addView(TextView(context).apply { text = "Card 4242 4242 4242 4242" })
        }.watchBlock(), LinearLayout.LayoutParams(MATCH_PARENT, 3 * pad))
        root.addView(Button(this).apply {
            text = "Report an error"
            setOnClickListener { AfribaseWatch.captureException(IllegalStateException("sample caught error")) }
        }, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        root.addView(Button(this).apply {
            text = "Open secure screen"
            setOnClickListener { startActivity(Intent(this@MainActivity, SecureActivity::class.java)) }
        })
        root.addView(Button(this).apply {
            text = "Crash"
            setOnClickListener { throw RuntimeException("sample crash") }
        })
        setContentView(root)
    }
}
