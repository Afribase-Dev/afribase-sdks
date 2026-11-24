# afribase-kotlin: Base1 Watch for Android

Crash and error reporting, UX signals, live presence and opt-in **wireframe
session replay** for native Android apps (Views and Jetpack Compose).

Replay never takes pixels: there is no screenshot, `PixelCopy` or
draw-to-bitmap anywhere in this SDK. It walks the view tree and records
boxes, kinds and masked text, so apps that block screen capture
(`FLAG_SECURE`) stay blocked. The wire format is
`watch-wireframe-contract.md` (v1), shared with the Swift SDK, the server
and the dashboard.

## Install

From Maven Central (after the first release):

```kotlin
implementation("io.github.afribase-dev:watch-android:0.1.1")
```

Or from JitPack now:

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven("https://jitpack.io")
    }
}

// app/build.gradle.kts
dependencies {
    implementation("com.github.Afribase-Dev:afribase-sdks:watch-0.1.1")
}
```

minSdk 24. No runtime dependencies. Compose and OkHttp support only switch on
when your app already has them.

## Start

```kotlin
class App : Application() {
    override fun onCreate() {
        super.onCreate()
        AfribaseWatch.init(
            this,
            WatchConfig(
                key = "abw_...",
                endpoint = "https://api.example.com/watch/ingest",
                release = BuildConfig.VERSION_NAME,
                environment = "production",
                replay = false,      // wireframe replay, opt-in
                live = true,         // live presence heartbeats
                maskAllText = true,  // replay: mask every label unless watchUnmask
                user = { session.userId },
            ),
        )
    }
}
```

| Option | Default | What it does |
| --- | --- | --- |
| `replay` | `false` | Wireframe replay. The target owner must also turn replay on in Watch settings, or the server refuses the upload. |
| `live` | `true` | Presence heartbeats. The server drops them unless the target owner turns live presence on. |
| `maskAllText` | `true` | Replay: every label masked unless it (or an ancestor) has `watchUnmask`. Inputs are masked either way. |
| `ux` | `true` | Rage taps, slow screens, errors after a tap, navigation loops. |
| `sampleRate` | `1.0` | Share of error events sent. |
| `slowScreenMs` | `3000` | A screen whose first frame takes longer is reported as `slow`. |
| `debug` | `false` | Log what is sent to logcat (tag `AfribaseWatch`). |
| `replayOnSecureWindows` | `false` | Replay: record a wireframe even on `FLAG_SECURE` windows (otherwise they are "secure screen" placeholders). No pixels are ever taken; on those windows all text is masked whatever `maskAllText` says. Screens marked `watchSecureScreen` stay placeholders. |

## Client API (same as the JS SDK)

| JS (`initWatch`) | Android |
| --- | --- |
| `captureError(err, context)` | `AfribaseWatch.captureError(e, mapOf(...))` (also `captureException`) |
| `flush()` | `AfribaseWatch.flush()` |
| `stop()` | `AfribaseWatch.stop()` |
| `log` events | `AfribaseWatch.log("message", context)` |
| `sessionId` | `AfribaseWatch.sessionId` |

## Events

Kinds `error`, `http`, `slow`, `log`, `ux`, with the JS fields: `message`,
`stack`, `url` (`app://<Screen>`), `method`, `status`, `durationMs`,
`release`, `environment`, `userId`, `sessionId`, the last 30 `breadcrumbs`,
`context`, `timestamp`, plus `platform: "android"`.

- Uncaught exceptions on any thread: the event is written to disk
  synchronously, then the previous handler runs (system crash dialog and
  other reporters keep working). Sent on the next launch.
- `sampleRate` applies to errors only, as in JS.
- Batching: at most 50 events / 256 KB per request, flushed every 5 s, as
  soon as 20 are waiting, when the app goes to the background and on `stop()`.
- Retry: events stay on disk until the server accepts them (2xx) or refuses
  them for good (4xx other than 408/429). Network errors, 5xx, 408 and 429
  back off 5 s, 10 s, 20 s ... up to 5 min.
- All network and disk work runs on one low-priority background thread; the
  main thread only records cheap facts (no ANRs from Watch).

### Breadcrumbs

`navigation` (`how`, `to`), `click` (the tapped view: class, kind, resource
id, button text only when unmasked), `fetch` (method, URL without query,
status, ms), `lifecycle`, `screen_load`, and your own via
`AfribaseWatch.addBreadcrumb`. Values are cleaned one by one: anything under a
secret name (password, token, api key, cookie ...) becomes `••••`, URLs lose
their query and fragment, numbers and times stay readable. The server masks
every value again.

## UX signals

The six signals of `watch-ux.ts`, same names and thresholds, structure only:

| Type | When (JS threshold) |
| --- | --- |
| `rage_click` | 3+ taps on the same element within 1 s, once per burst |
| `dead_click` | a tap on a clickable view (not a field or toggle) and nothing reacts within 1 s: no layout change, screen change or request; once per element per 5 s |
| `form_abandon` | fields on a screen were typed into, then the screen or app was left with no request within 1.5 s of a tap; reports the screen, the last field (resource id, else hint) and its type, never values |
| `error_after_action` | an error within 2 s of a tap, with the element |
| `nav_loop` | screens A → B → A → B within 30 s |
| `slow_interaction` | tap or key to the next frame over 500 ms (click handlers included); once per element per 10 s |

Plus a `slow` event when an Activity's first frame takes over
`slowScreenMs` (3 s). At most 50 signals per launch.

## Screens

Activities are named automatically (`CheckoutActivity`). Single-Activity
apps (Compose navigation, fragments) name screens themselves:

```kotlin
navController.addOnDestinationChangedListener { _, dest, _ -> AfribaseWatch.setScreen(dest.route ?: "unknown") }
```

## Linking app sessions to backend errors

```kotlin
val http = OkHttpClient.Builder().addInterceptor(WatchInterceptor()).build()
```

Adds `X-Watch-Session: <sessionId>` to your requests (the Python SDK reads
it), records each request as a breadcrumb (method, URL without query,
status, ms), reports 5xx and network failures as `http` events and requests
over 4 s as `slow` events, and tells the UX signals a request happened. Bodies
and headers are never read. `WatchInterceptor(captureHttp = false)` only adds
the header. Other HTTP clients: send `AfribaseWatch.sessionId` yourself.

## Wireframe replay

Every 500 ms (at most) the SDK walks the current Activity's window on the
main thread, and turns it into a `snapshot` only when the tree changed, plus a
keyframe every 10 s. A walk over 4 ms makes the next tick(s) skip; a walk is
cut off at 16 ms and marked `truncated`. Serialising and gzip happen on the
background thread. The last 60 s are kept (always starting at a snapshot) and
uploaded once, 5 s after an error or UX event, at most once per 30 s and 10
times per launch. After a crash the buffer is written to disk and uploaded on
the next launch.

Recorded: `snapshot`, `screen`, `touch` (down / up / move every 100 ms),
`scroll` (ScrollView / NestedScrollView offsets), `keyboard` (Android 11+),
`lifecycle`, `error` (masked message).

### Privacy rules

- Text is masked (`*` per character, length kept, capped at 40) unless
  unmasked; inputs are always masked; password, one-time-code and card
  fields send `"text": null` (no length). Detected by input type, password
  transformation, autofill hints and resource id names (`password`, `otp`,
  `cvv`, `card`, `pin`...). Compose: `SemanticsProperties.Password`.
- `FLAG_SECURE` on the window, or `watchSecureScreen` anywhere in the tree:
  `"secure": true, "root": null`, touches without coordinates, no scroll or
  keyboard events, no error markers.
- `WebView`: a `web` box, content never read.
- No network bodies, logs, clipboard or accessibility labels.

### Markers

Views (Kotlin / Java / XML):

```kotlin
cardForm.watchBlock()          // WatchMarkers.watchBlock(cardForm) from Java
promoBanner.watchUnmask()
pinScreenRoot.watchSecureScreen()
```
```xml
<LinearLayout android:tag="watchBlock" ... />
```

Compose:

```kotlin
import com.afribase.watch.compose.*

Column(Modifier.watchBlock()) { CardForm() }
Text("Welcome", Modifier.watchUnmask())
Box(Modifier.watchSecureScreen()) { PinPad() }
```

Compose is read through the semantics tree (roles, text, editable text,
password, scroll ranges), found at runtime via `ViewRootForTest`; Compose is
a `compileOnly` dependency.

## Limits (0.1.0)

- `form_abandon`: a keyboard "Send"/"Done" action is not seen as a submit
  unless it makes a request through `WatchInterceptor` (Android has no
  global hook for IME actions without replacing your listener).
- HTTP instrumentation covers OkHttp only (Retrofit, Coil, Ktor-OkHttp use
  it); `HttpURLConnection` calls are not seen.
- There is no `console.error` on Android: use `AfribaseWatch.log` or
  `addBreadcrumb`.

- Only the Activity's own window is walked: dialogs, popups, bottom sheets in
  their own window and toasts are not in the wireframe.
- `AndroidView` interop inside Compose is not descended into.
- Colours: solid `ColorDrawable` / `GradientDrawable` backgrounds and text
  colour only; images are grey `image` boxes.
- Compose nodes carry no colours.
- Session: one per process start, renewed after 30 min in the background.

## Develop

```bash
./gradlew test                     # 66 JVM tests (Robolectric for the View walker)
./gradlew :sample:assembleDebug    # sample app, posts to http://10.0.2.2:8787/watch/ingest
```
