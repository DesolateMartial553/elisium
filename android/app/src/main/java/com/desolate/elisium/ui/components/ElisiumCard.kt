package com.desolate.elisium.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

/**
 * Raised card: `raised` tone, medium radius, 1dp outline. [active] swaps the outline for the glow gradient
 * (one selected or running card). Padding is generous and there are no fixed heights.
 */
@Composable
fun ElisiumCard(
    modifier: Modifier = Modifier,
    active: Boolean = false,
    interactionSource: MutableInteractionSource? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val extras = ElisiumTheme.extras
    val shape = MaterialTheme.shapes.medium
    val border = if (active) BorderStroke(1.dp, extras.glowBrush()) else BorderStroke(1.dp, extras.outline)
    val ring = if (interactionSource != null) Modifier.focusRing(interactionSource, shape) else Modifier
    Surface(
        modifier = modifier.fillMaxWidth().then(ring),
        shape = shape,
        color = extras.raised,
        contentColor = MaterialTheme.colorScheme.onSurface,
        border = border,
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
    }
}

@AfterglowPreviews
@Composable
private fun ElisiumCardPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ElisiumCard { Text("A plain card", style = MaterialTheme.typography.titleMedium) }
                ElisiumCard(active = true) { Text("A selected card", style = MaterialTheme.typography.titleMedium) }
            }
        }
    }
}
