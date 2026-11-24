plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.afribase.watch.sample"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.afribase.watch.sample"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        // The emulator reaches the Mac's localhost at 10.0.2.2.
        buildConfigField("String", "WATCH_ENDPOINT", "\"http://10.0.2.2:8787/watch/ingest\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = "11"
    }
}

dependencies {
    implementation(project(":watch"))
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
