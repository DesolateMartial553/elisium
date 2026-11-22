package com.desolate.elisium.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.NumericStyle
import com.desolate.elisium.ui.theme.PillShape
import com.desolate.elisium.ui.theme.Sizes

/**
 * A 36dp filter chip inside a 44dp touch target. Selected = a 1.5dp `hue` outline (the hue's one allowed use
 * besides progress and focus). [count] may be null (a plain choice chip). [description] is the spoken name.
 */
@Composable
fun FilterChip(
    label: String,
    count: Int?,
    selected: Boolean,
    onClick: () -> Unit,
    description: String,
    modifier: Modifier = Modifier,
) {
    val extras = ElisiumTheme.extras
    val source = remember { MutableInteractionSource() }
    Box(
        modifier
            .heightIn(min = Sizes.MIN_TARGET.dp)
            .focusRing(source, PillShape)
            .selectable(selected = selected, interactionSource = source, indication = null, role = Role.RadioButton, onClick = onClick)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.height(Sizes.CHIP.dp)
                .background(extras.surface, PillShape)
                .then(if (selected) Modifier.border(1.5.dp, extras.hue, PillShape) else Modifier)
                .padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                label,
                style = MaterialTheme.typography.bodyMedium,
                color = if (selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (count != null) {
                Text(
                    count.toString(),
                    style = MaterialTheme.typography.labelLarge.merge(NumericStyle),
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}
