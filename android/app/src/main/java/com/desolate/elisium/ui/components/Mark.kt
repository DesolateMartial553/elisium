package com.desolate.elisium.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

/** The mark: three stacked rounded bars getting shorter (a queue), the last one in `hue`. Decorative. */
@Composable
fun ElisiumMark(modifier: Modifier = Modifier, size: Dp = 22.dp) {
    val ink = MaterialTheme.colorScheme.onBackground
    val hue = ElisiumTheme.extras.hue
    Canvas(modifier.size(size).clearAndSetSemantics { }) {
        val u = this.size.minDimension / 22f
        fun bar(x: Float, y: Float, w: Float, color: androidx.compose.ui.graphics.Color) =
            drawRoundRect(color, Offset(x * u, y * u), Size(w * u, 4f * u), CornerRadius(2f * u))
        bar(2f, 3f, 18f, ink.copy(alpha = 0.35f))
        bar(2f, 9f, 13f, ink.copy(alpha = 0.6f))
        bar(2f, 15f, 8f, hue)
    }
}
