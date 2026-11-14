package com.desolate.elisium.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme

/**
 * Top of a main screen: a faint glow band (the gradient at about 15% opacity fading into the background)
 * behind a large gradient-filled title. Sits under the status bar (edge to edge).
 */
@Composable
fun HorizonHeader(title: String, modifier: Modifier = Modifier, actions: @Composable RowScope.() -> Unit = {}) {
    val extras = ElisiumTheme.extras
    val glow = extras.glowColors.map { it.copy(alpha = 0.16f) }
    val fade = Brush.verticalGradient(listOf(Color.Transparent, extras.bg))
    Box(
        modifier = modifier.fillMaxWidth().drawBehind {
            drawRect(Brush.horizontalGradient(glow))
            drawRect(fade)
        },
    ) {
        Row(
            Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(start = 20.dp, end = 8.dp, top = 12.dp, bottom = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                modifier = Modifier.weight(1f).semantics { heading() },
                style = MaterialTheme.typography.headlineMedium.copy(brush = extras.glowBrush()),
            )
            actions()
        }
    }
}

@AfterglowPreviews
@Composable
private fun HorizonHeaderPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) { HorizonHeader("Elisium") }
    }
}
