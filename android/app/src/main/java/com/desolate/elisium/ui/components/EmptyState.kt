package com.desolate.elisium.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

/** A large soft glowing arrow-into-tray glyph (the app icon) and one warm sentence. The glyph is decorative. */
@Composable
fun EmptyState(message: String, modifier: Modifier = Modifier) {
    val extras = ElisiumTheme.extras
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Canvas(Modifier.size(132.dp).clearAndSetSemantics { }) {
            val c = Offset(size.width / 2f, size.height / 2f)
            // Soft halo
            drawCircle(
                Brush.radialGradient(
                    listOf(extras.glowB.copy(alpha = 0.32f), extras.glowA.copy(alpha = 0.14f), Color.Transparent),
                    center = c, radius = size.minDimension / 2f,
                ),
                radius = size.minDimension / 2f, center = c,
            )
            val u = size.minDimension / 108f
            val stroke = Stroke(width = 9f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
            val brush = Brush.verticalGradient(listOf(extras.glowA, extras.glowB, extras.glowC), startY = 22f * u, endY = 90f * u)
            val arrow = Path().apply {
                moveTo(54f * u, 24f * u); lineTo(54f * u, 62f * u)
                moveTo(36f * u, 47f * u); lineTo(54f * u, 65f * u); lineTo(72f * u, 47f * u)
            }
            val tray = Path().apply {
                moveTo(28f * u, 82f * u); lineTo(80f * u, 82f * u)
            }
            // Glow pass (wide, faint) then the crisp glyph
            val wide = Stroke(width = 20f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
            drawPath(arrow, extras.glowB.copy(alpha = 0.18f), style = wide)
            drawPath(tray, extras.glowC.copy(alpha = 0.18f), style = wide)
            drawPath(arrow, brush, style = stroke)
            drawPath(tray, brush, style = stroke)
        }
        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

@AfterglowPreviews
@Composable
private fun EmptyStatePreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) { EmptyState("Paste a link to begin.") }
    }
}
