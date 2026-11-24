package com.afribase.watch.compose

import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsPropertyKey
import androidx.compose.ui.semantics.semantics

/**
 * Replay markers for Jetpack Compose. They add a semantics property that
 * the wireframe recorder reads; accessibility services ignore it.
 *
 *     Column(Modifier.watchBlock()) { CardForm() }
 */
object WatchSemantics {
    val Block = SemanticsPropertyKey<Boolean>("AfribaseWatchBlock")
    val Unmask = SemanticsPropertyKey<Boolean>("AfribaseWatchUnmask")
    val SecureScreen = SemanticsPropertyKey<Boolean>("AfribaseWatchSecureScreen")
}

/** Sends this element as one `blocked` box: no children, no text. */
fun Modifier.watchBlock(): Modifier = semantics { set(WatchSemantics.Block, true) }

/** Sends the real text of this element and its children (inputs stay masked). */
fun Modifier.watchUnmask(): Modifier = semantics { set(WatchSemantics.Unmask, true) }

/** Treats the whole screen holding this element as secure: no wireframe at all. */
fun Modifier.watchSecureScreen(): Modifier = semantics { set(WatchSemantics.SecureScreen, true) }
