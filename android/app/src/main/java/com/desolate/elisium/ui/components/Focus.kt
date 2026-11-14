package com.desolate.elisium.ui.components

import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.unit.dp
import androidx.compose.material3.MaterialTheme

/** A visible 2dp accent ring while [interactionSource] has focus (keyboard / switch access). Never removed. */
@Composable
fun Modifier.focusRing(interactionSource: InteractionSource, shape: Shape): Modifier {
    val focused by interactionSource.collectIsFocusedAsState()
    if (!focused) return this
    val color = MaterialTheme.colorScheme.primary
    return this.drawWithContent {
        drawContent()
        val width = 2.dp.toPx()
        val outline = shape.createOutline(Size(size.width - width, size.height - width), layoutDirection, this)
        translate(width / 2f, width / 2f) {
            drawOutline(outline, color, style = Stroke(width))
        }
    }
}
