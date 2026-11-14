package com.desolate.elisium.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion

/**
 * Rounded input whose border turns accent and which gets a soft glow-gradient halo while focused
 * (the border itself stays a solid 2dp accent line, so focus is visible without the halo too).
 */
@Composable
fun ElisiumTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    supportingText: String? = null,
    isError: Boolean = false,
    singleLine: Boolean = false,
    maxLines: Int = if (singleLine) 1 else Int.MAX_VALUE,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
) {
    val extras = ElisiumTheme.extras
    val source = remember { MutableInteractionSource() }
    val focused by source.collectIsFocusedAsState()
    val halo by animateFloatAsState(
        if (focused) 1f else 0f, Motion.spec(Motion.FAST_MS, extras.reducedMotion), label = "fieldHalo",
    )
    val shape = MaterialTheme.shapes.medium
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth().drawBehind {
            if (halo > 0f) {
                val brush = androidx.compose.ui.graphics.Brush.horizontalGradient(extras.glowColors)
                for (i in 3 downTo 1) {
                    val grow = i * 3.dp.toPx()
                    drawRoundRect(
                        brush,
                        topLeft = Offset(-grow, -grow),
                        size = Size(size.width + grow * 2, size.height + grow * 2),
                        cornerRadius = CornerRadius(16.dp.toPx() + grow),
                        alpha = 0.07f * halo,
                    )
                }
            }
        },
        label = { Text(label) },
        supportingText = supportingText?.let { { Text(it) } },
        isError = isError,
        singleLine = singleLine,
        maxLines = maxLines,
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        interactionSource = source,
        shape = shape,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = MaterialTheme.colorScheme.primary,
            unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            errorBorderColor = MaterialTheme.colorScheme.error,
            focusedContainerColor = extras.raised,
            unfocusedContainerColor = extras.raised,
            errorContainerColor = extras.raised,
            focusedLabelColor = MaterialTheme.colorScheme.primary,
            unfocusedLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
            cursorColor = MaterialTheme.colorScheme.primary,
        ),
    )
}

@AfterglowPreviews
@Composable
private fun ElisiumTextFieldPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ElisiumTextField("https://example.com/video", {}, "Link to download", supportingText = "Paste one link")
                ElisiumTextField("2m", {}, "Speed limit", isError = true, supportingText = "Not saved yet")
            }
        }
    }
}
