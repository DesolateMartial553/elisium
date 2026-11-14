package com.desolate.elisium.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

/** Which icon and tint a queue/history state gets. Pure so it can be tested. */
enum class ChipKind { Waiting, Active, Working, Paused, Done, Failed, Stopped }

fun chipKindOf(state: String): ChipKind = when (state) {
    "downloading" -> ChipKind.Active
    "probing", "merging", "converting" -> ChipKind.Working
    "paused" -> ChipKind.Paused
    "done" -> ChipKind.Done
    "failed" -> ChipKind.Failed
    "cancelled", "skipped" -> ChipKind.Stopped
    else -> ChipKind.Waiting
}

/**
 * Small pill with an icon and the state as a word, tinted from the semantic tokens. The word is
 * always shown in the normal text colour (colour is never the only carrier of the state).
 */
@Composable
fun StateChip(state: String, label: String, modifier: Modifier = Modifier) {
    val kind = chipKindOf(state)
    val extras = ElisiumTheme.extras
    val scheme = MaterialTheme.colorScheme
    val tint: Color = when (kind) {
        ChipKind.Active -> scheme.primary
        ChipKind.Working -> extras.glowB
        ChipKind.Done -> extras.success
        ChipKind.Failed -> extras.error
        ChipKind.Paused -> extras.warning
        ChipKind.Waiting, ChipKind.Stopped -> scheme.onSurfaceVariant
    }
    Surface(
        modifier = modifier,
        shape = CircleShape,
        color = tint.copy(alpha = 0.14f),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.45f)),
    ) {
        Row(
            Modifier.padding(start = 10.dp, end = 12.dp, top = 5.dp, bottom = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            ChipIcon(kind, tint)
            Text(label, style = MaterialTheme.typography.labelLarge, color = scheme.onSurface)
        }
    }
}

@Composable
private fun ChipIcon(kind: ChipKind, tint: Color) {
    if (kind == ChipKind.Paused) {
        Canvas(Modifier.size(16.dp)) {
            val w = size.width * 0.26f
            val r = CornerRadius(w / 2f, w / 2f)
            drawRoundRect(tint, Offset(size.width * 0.18f, size.height * 0.12f), Size(w, size.height * 0.76f), r)
            drawRoundRect(tint, Offset(size.width * 0.56f, size.height * 0.12f), Size(w, size.height * 0.76f), r)
        }
        return
    }
    val icon: ImageVector = when (kind) {
        ChipKind.Active -> Icons.Filled.KeyboardArrowDown
        ChipKind.Working -> Icons.Filled.Refresh
        ChipKind.Done -> Icons.Filled.Check
        ChipKind.Failed -> Icons.Filled.Warning
        ChipKind.Stopped -> Icons.Filled.Close
        else -> Icons.AutoMirrored.Filled.List
    }
    Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(16.dp))
}

@AfterglowPreviews
@Composable
private fun StateChipPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (s in listOf("queued", "downloading", "merging", "paused", "done", "failed", "cancelled")) {
                    StateChip(s, s.replaceFirstChar { it.uppercase() })
                }
            }
        }
    }
}
