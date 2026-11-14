package com.desolate.elisium.ui.components

import androidx.compose.animation.core.Animatable
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion
import kotlinx.coroutines.launch

/**
 * Card enter: fade in and rise 8dp over the base duration. Does nothing when [animate] is false
 * (already shown once) or motion is reduced.
 */
@Composable
fun Modifier.enterRise(animate: Boolean): Modifier {
    val reduced = ElisiumTheme.extras.reducedMotion
    if (!animate || reduced) return this
    val progress = remember { Animatable(0f) }
    LaunchedEffect(Unit) {
        launch { progress.animateTo(1f, Motion.spec(Motion.BASE_MS, false)) }
    }
    return this.graphicsLayer {
        alpha = progress.value
        translationY = (1f - progress.value) * 8.dp.toPx()
    }
}
