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
import com.desolate.elisium.ui.theme.ElisiumTheme

/** A visible 2dp `focus` outline with a 2dp offset while [interactionSource] has focus (keyboard / switch access). Never removed. */
@Composable
fun Modifier.focusRing(interactionSource: InteractionSource, shape: Shape): Modifier {
    val focused by interactionSource.collectIsFocusedAsState()
    if (!focused) return this
    val color = ElisiumTheme.extras.focus
    return this.drawWithContent {
        drawContent()
        val width = 2.dp.toPx()
        val grow = 2.dp.toPx() + width / 2f
        val outline = shape.createOutline(Size(size.width + grow * 2, size.height + grow * 2), layoutDirection, this)
        translate(-grow, -grow) {
            drawOutline(outline, color, style = Stroke(width))
        }
    }
}
