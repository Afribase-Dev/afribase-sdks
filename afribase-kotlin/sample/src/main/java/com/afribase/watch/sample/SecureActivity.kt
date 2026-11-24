package com.afribase.watch.sample

import android.app.Activity
import android.os.Bundle
import android.view.WindowManager
import android.widget.TextView

/** FLAG_SECURE: Watch sends `secure: true, root: null` here. */
class SecureActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(TextView(this).apply { text = "Secret balance: 1,000,000" })
    }
}
