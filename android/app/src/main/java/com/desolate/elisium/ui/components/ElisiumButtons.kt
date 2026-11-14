package com.desolate.elisium.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

private val Pill = RoundedCornerShape(50)
private val ButtonPadding = PaddingValues(horizontal = 20.dp, vertical = 10.dp)

private fun Modifier.target(description: String?): Modifier {
    val base = this.heightIn(min = 48.dp)
    return if (description != null) base.semantics { contentDescription = description } else base
}

/** Filled accent pill: at least 48dp tall, 2dp accent focus ring. [description] overrides the spoken name. */
@Composable
fun ElisiumButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    description: String? = null,
) {
    val source = remember { MutableInteractionSource() }
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = Pill,
        contentPadding = ButtonPadding,
        interactionSource = source,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
            disabledContainerColor = ElisiumTheme.extras.outline,
            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
        modifier = modifier.target(description).focusRing(source, Pill),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** Outlined pill with the stronger outline token; same size and focus rules as [ElisiumButton]. */
@Composable
fun ElisiumOutlinedButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    description: String? = null,
) {
    val source = remember { MutableInteractionSource() }
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = Pill,
        contentPadding = ButtonPadding,
        interactionSource = source,
        border = BorderStroke(1.dp, if (enabled) MaterialTheme.colorScheme.outline else ElisiumTheme.extras.outline),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
        modifier = modifier.target(description).focusRing(source, Pill),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** Flat accent text button (dialogs). */
@Composable
fun ElisiumTextButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    description: String? = null,
) {
    val source = remember { MutableInteractionSource() }
    TextButton(
        onClick = onClick,
        shape = Pill,
        interactionSource = source,
        modifier = modifier.target(description).focusRing(source, Pill),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

@AfterglowPreviews
@Composable
private fun ElisiumButtonsPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ElisiumButton("Add", {})
                ElisiumButton("Add", {}, enabled = false)
                ElisiumOutlinedButton("Pause", {})
                ElisiumTextButton("Keep it", {})
            }
        }
    }
}
