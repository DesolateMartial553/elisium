package com.desolate.elisium.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion
import com.desolate.elisium.ui.theme.Sizes

/** Fraction 0..1 for a percent that may be null, NaN or outside 0..100 (all become safe values). */
fun progressFraction(percent: Int?): Float = ((percent ?: 0) / 100f).coerceIn(0f, 1f)

/**
 * The 4dp progress bar: `hue` on `track`, flat, no gradient or glow. Paused is drawn in `faint`. A null
 * [fraction] (unknown) shows only the track; the row's words say what is happening. The fill eases over the base
 * duration (instantly when motion is reduced). The bar itself is silent: the row speaks the percent.
 */
@Composable
fun FlatProgress(fraction: Float?, paused: Boolean, modifier: Modifier = Modifier) {
    val extras = ElisiumTheme.extras
    val shown by animateFloatAsState(
        (fraction ?: 0f).coerceIn(0f, 1f), Motion.spec(Motion.BASE_MS, extras.reducedMotion), label = "fill",
    )
    val radius = RoundedCornerShape((Sizes.PROGRESS / 2).dp)
    Box(
        modifier.fillMaxWidth().height(Sizes.PROGRESS.dp).clip(radius).background(extras.track).clearAndSetSemantics { },
    ) {
        if (shown > 0f) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(shown).background(if (paused) extras.faint else extras.hue))
        }
    }
}
