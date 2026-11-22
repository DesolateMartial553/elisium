package com.desolate.elisium.ui.components

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.PillShape
import com.desolate.elisium.ui.theme.Sizes

private val ButtonPadding = PaddingValues(horizontal = 18.dp, vertical = 8.dp)

private fun Modifier.target(description: String?): Modifier {
    val base = this.heightIn(min = Sizes.MIN_TARGET.dp)
    return if (description != null) base.semantics { contentDescription = description } else base
}

/** The primary action: an inverted pill (white with black text at night, black with white by day), 44dp tall at least. */
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
        shape = PillShape,
        contentPadding = ButtonPadding,
        interactionSource = source,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
            disabledContainerColor = ElisiumTheme.extras.raised,
            disabledContentColor = ElisiumTheme.extras.faint,
        ),
        modifier = modifier.target(description).focusRing(source, PillShape),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** A quiet secondary pill: `raised` fill, no border, text colour. Same size and focus rules as [ElisiumButton]. */
@Composable
fun ElisiumQuietButton(
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
        shape = PillShape,
        contentPadding = ButtonPadding,
        interactionSource = source,
        colors = ButtonDefaults.buttonColors(
            containerColor = ElisiumTheme.extras.raised,
            contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContainerColor = ElisiumTheme.extras.raised,
            disabledContentColor = ElisiumTheme.extras.faint,
        ),
        modifier = modifier.target(description).focusRing(source, PillShape),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** Flat text action in the text colour (dialogs, row links such as "Open"). No hue: the accent is for progress only. */
@Composable
fun ElisiumTextButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    description: String? = null,
) {
    val source = remember { MutableInteractionSource() }
    TextButton(
        onClick = onClick,
        enabled = enabled,
        shape = PillShape,
        interactionSource = source,
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        colors = ButtonDefaults.textButtonColors(
            contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContentColor = ElisiumTheme.extras.faint,
        ),
        modifier = modifier.target(description).focusRing(source, PillShape),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}
