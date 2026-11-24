package com.afribase.watch.sample

import android.app.Application
import com.afribase.watch.AfribaseWatch
import com.afribase.watch.WatchConfig

class SampleApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AfribaseWatch.init(
            this,
            WatchConfig(
                key = "abw_sample",
                endpoint = BuildConfig.WATCH_ENDPOINT,
                release = "sample@" + BuildConfig.VERSION_NAME,
                environment = "dev",
                replay = true,
                debug = true,
            ),
        )
    }
}
