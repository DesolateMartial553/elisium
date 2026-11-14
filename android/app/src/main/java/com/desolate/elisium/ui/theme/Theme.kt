package com.desolate.elisium.ui.theme

import android.content.Context
import android.content.ContextWrapper
import android.graphics.Color as AndroidColor
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import com.desolate.elisium.settings.Appearance

/** Extras Material has no slot for: the glow, semantic colours, the raised tone and the reduced-motion flag. */
@Immutable
data class ElisiumExtras(
    val glowA: Color,
    val glowB: Color,
    val glowC: Color,
    val success: Color,
    val warning: Color,
    val error: Color,
    val raised: Color,
    val bg: Color,
    val outline: Color,
    val outlineStrong: Color,
    val isDark: Boolean,
    val reducedMotion: Boolean,
) {
    val glowColors: List<Color> get() = listOf(glowA, glowB, glowC)
    fun glowBrush(): Brush = Brush.horizontalGradient(glowColors)
}

val LocalElisiumExtras = staticCompositionLocalOf { extrasOf(NightPalette, true, false) }

/** `ElisiumTheme.extras` reads the current [ElisiumExtras]. */
object ElisiumTheme {
    val extras: ElisiumExtras
        @Composable @ReadOnlyComposable get() = LocalElisiumExtras.current
}

fun extrasOf(p: AfterglowPalette, dark: Boolean, reducedMotion: Boolean) = ElisiumExtras(
    glowA = p.glowA, glowB = p.glowB, glowC = p.glowC,
    success = p.success, warning = p.warning, error = p.error,
    raised = p.raised, bg = p.bg, outline = p.outline, outlineStrong = p.outlineStrong,
    isDark = dark, reducedMotion = reducedMotion,
)

/** Token palette -> Material colour scheme. `outline` is outlineStrong (control borders), `outlineVariant` is outline. */
fun colorSchemeOf(p: AfterglowPalette, dark: Boolean): ColorScheme {
    return if (dark) {
        darkColorScheme(
            primary = p.accent, onPrimary = p.onAccent,
            primaryContainer = p.raised, onPrimaryContainer = p.text,
            secondary = p.accent, onSecondary = p.onAccent,
            secondaryContainer = p.raised, onSecondaryContainer = p.text,
            tertiary = p.accent, onTertiary = p.onAccent,
            tertiaryContainer = p.raised, onTertiaryContainer = p.text,
            background = p.bg, onBackground = p.text,
            surface = p.surface, onSurface = p.text,
            surfaceVariant = p.raised, onSurfaceVariant = p.muted,
            surfaceTint = p.accent,
            inverseSurface = p.text, inverseOnSurface = p.bg, inversePrimary = p.accent,
            error = p.error, onError = p.bg,
            errorContainer = p.raised, onErrorContainer = p.error,
            outline = p.outlineStrong, outlineVariant = p.outline,
            scrim = Color.Black,
            surfaceBright = p.raised, surfaceDim = p.bg,
            surfaceContainerLowest = p.bg, surfaceContainerLow = p.surface, surfaceContainer = p.surface,
            surfaceContainerHigh = p.raised, surfaceContainerHighest = p.raised,
        )
    } else {
        lightColorScheme(
            primary = p.accent, onPrimary = p.onAccent,
            primaryContainer = p.raised, onPrimaryContainer = p.text,
            secondary = p.accent, onSecondary = p.onAccent,
            secondaryContainer = p.raised, onSecondaryContainer = p.text,
            tertiary = p.accent, onTertiary = p.onAccent,
            tertiaryContainer = p.raised, onTertiaryContainer = p.text,
            background = p.bg, onBackground = p.text,
            surface = p.surface, onSurface = p.text,
            surfaceVariant = p.raised, onSurfaceVariant = p.muted,
            surfaceTint = p.accent,
            inverseSurface = p.text, inverseOnSurface = p.bg, inversePrimary = p.accent,
            error = p.error, onError = p.bg,
            errorContainer = p.raised, onErrorContainer = p.error,
            outline = p.outlineStrong, outlineVariant = p.outline,
            scrim = Color.Black,
            surfaceBright = p.surface, surfaceDim = p.raised,
            surfaceContainerLowest = p.surface, surfaceContainerLow = p.surface, surfaceContainer = p.surface,
            surfaceContainerHigh = p.raised, surfaceContainerHighest = p.raised,
        )
    }
}

/** Whether to draw Nightfall: forced by [Appearance], else the system setting (Nightfall when unsure). */
fun useNight(appearance: Appearance, systemDark: Boolean): Boolean = when (appearance) {
    Appearance.Night -> true
    Appearance.Day -> false
    Appearance.System -> systemDark
}

private tailrec fun Context.findActivity(): ComponentActivity? = when (this) {
    is ComponentActivity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

/**
 * The Afterglow theme. Dynamic colour is not used at all (it would erase the identity). Draws edge to edge
 * with status/navigation bar icons that contrast with the chosen theme. Compile-verified only.
 */
@Composable
fun ElisiumTheme(
    appearance: Appearance = Appearance.System,
    reduceMotion: Boolean = false,
    content: @Composable () -> Unit,
) {
    val dark = useNight(appearance, isSystemInDarkTheme())
    val context = LocalContext.current
    val reduced = isReducedMotion(
        reduceMotion,
        try {
            Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f)
        } catch (_: Exception) {
            1f
        },
    )
    val palette = if (dark) NightPalette else DayPalette
    val scheme = remember(dark) { colorSchemeOf(palette, dark) }
    val extras = remember(dark, reduced) { extrasOf(palette, dark, reduced) }

    val activity = remember(context) { context.findActivity() }
    if (activity != null) {
        DisposableEffect(activity, dark) {
            val bars = if (dark) {
                SystemBarStyle.dark(AndroidColor.TRANSPARENT)
            } else {
                SystemBarStyle.light(AndroidColor.TRANSPARENT, AndroidColor.TRANSPARENT)
            }
            activity.enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
            onDispose { }
        }
    }

    CompositionLocalProvider(LocalElisiumExtras provides extras) {
        MaterialTheme(colorScheme = scheme, typography = ElisiumTypography, shapes = ElisiumShapes, content = content)
    }
}
