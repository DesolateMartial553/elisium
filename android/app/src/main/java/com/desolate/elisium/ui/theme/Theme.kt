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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import com.desolate.elisium.settings.Appearance

/** Tokens Material has no slot for (raised, control, faint, hue, track, the tones) and the reduced-motion flag. */
@Immutable
data class ElisiumExtras(
    val palette: ShelfPalette,
    val isDark: Boolean,
    val reducedMotion: Boolean,
) {
    val ground: Color get() = palette.ground
    val surface: Color get() = palette.surface
    val raised: Color get() = palette.raised
    val control: Color get() = palette.control
    val faint: Color get() = palette.faint
    val hue: Color get() = palette.hue
    val track: Color get() = palette.track
    val positive: Color get() = palette.positive
    val negative: Color get() = palette.negative
    val warning: Color get() = palette.warning
    val focus: Color get() = palette.focus
}

val LocalElisiumExtras = staticCompositionLocalOf { extrasOf(NightPalette, true, false) }

/** `ElisiumTheme.extras` reads the current [ElisiumExtras]. */
object ElisiumTheme {
    val extras: ElisiumExtras
        @Composable @ReadOnlyComposable get() = LocalElisiumExtras.current
}

fun extrasOf(p: ShelfPalette, dark: Boolean, reducedMotion: Boolean) = ElisiumExtras(p, dark, reducedMotion)

/**
 * Token palette -> Material colour scheme. Elevation is by lightness alone: ground < surface < raised,
 * so every container slot maps to one of those three and the surface tint is off.
 */
fun colorSchemeOf(p: ShelfPalette, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = p.primary, onPrimary = p.onPrimary,
        primaryContainer = p.raised, onPrimaryContainer = p.text,
        secondary = p.primary, onSecondary = p.onPrimary,
        secondaryContainer = p.raised, onSecondaryContainer = p.text,
        tertiary = p.primary, onTertiary = p.onPrimary,
        tertiaryContainer = p.raised, onTertiaryContainer = p.text,
        background = p.ground, onBackground = p.text,
        surface = p.surface, onSurface = p.text,
        surfaceVariant = p.raised, onSurfaceVariant = p.muted,
        surfaceTint = Color.Transparent,
        inverseSurface = p.text, inverseOnSurface = p.ground, inversePrimary = p.primary,
        error = p.negative, onError = p.ground,
        errorContainer = p.raised, onErrorContainer = p.negative,
        outline = p.control, outlineVariant = p.raised,
        scrim = Color.Black,
        surfaceBright = p.raised, surfaceDim = p.ground,
        surfaceContainerLowest = p.ground, surfaceContainerLow = p.surface, surfaceContainer = p.surface,
        surfaceContainerHigh = p.raised, surfaceContainerHighest = p.raised,
    )
}

/** Whether to draw the dark set: forced by [Appearance], else the system setting. */
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
 * The Night shelf theme, dark and light following the system (or the Appearance setting). Dynamic colour is
 * not used. Draws edge to edge with status/navigation bar icons that contrast with the chosen set.
 * Compile-verified only.
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
