import com.vanniktech.maven.publish.AndroidSingleVariantLibrary
import com.vanniktech.maven.publish.SonatypeHost

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("com.vanniktech.maven.publish")
}

android {
    namespace = "com.afribase.watch"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
        buildConfigField("String", "SDK_VERSION", "\"0.2.0\"")
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

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    // Optional: detected at runtime. The app brings its own copy.
    compileOnly("androidx.compose.ui:ui:1.6.8")
    compileOnly("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.12.2")
    testImplementation("androidx.test:core:1.5.0")
    testImplementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

// Maven Central (Sonatype Central Portal) as io.github.afribase-dev:watch-android, and
// JitPack (jitpack.yml at the repo root runs publishToMavenLocal).
// Credentials and the signing key come from Gradle properties / env vars,
// never from this file:
//   mavenCentralUsername / mavenCentralPassword   (Central Portal user token)
//   signingInMemoryKey / signingInMemoryKeyPassword (ASCII-armored GPG key)
// as ORG_GRADLE_PROJECT_<name> in CI, or in ~/.gradle/gradle.properties.
val publishGroup = (findProperty("publishGroup") as String?) ?: "io.github.afribase-dev"
val publishVersion = (findProperty("publishVersion") as String?) ?: "0.2.0"

mavenPublishing {
    configure(AndroidSingleVariantLibrary(variant = "release", sourcesJar = true, publishJavadocJar = true))
    publishToMavenCentral(SonatypeHost.CENTRAL_PORTAL)
    if (findProperty("signingInMemoryKey") != null) signAllPublications()

    coordinates(publishGroup, "watch-android", publishVersion)

    pom {
        name.set("Afribase Watch for Android")
        description.set("Base1 Watch for Android: errors, slow requests, UX signals, live presence and wireframe session replay that never captures pixels.")
        inceptionYear.set("2026")
        url.set("https://github.com/Afribase-Dev/afribase-sdks")
        licenses {
            license {
                name.set("Apache-2.0")
                url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("afribase")
                name.set("Afribase")
                url.set("https://useafribase.app")
            }
        }
        scm {
            url.set("https://github.com/Afribase-Dev/afribase-sdks")
            connection.set("scm:git:https://github.com/Afribase-Dev/afribase-sdks.git")
            developerConnection.set("scm:git:ssh://git@github.com/Afribase-Dev/afribase-sdks.git")
        }
    }
}
