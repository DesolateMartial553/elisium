package com.desolate.elisium.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Night shelf colour tokens, copied from `design/tokens.json` (a JVM test reads that file and
 * fails if they drift). Never add a colour here that is not in the token file.
 */
data class ShelfPalette(
    val ground: Color,
    val surface: Color,
    val raised: Color,
    val control: Color,
    val text: Color,
    val muted: Color,
    val faint: Color,
    val hue: Color,
    val track: Color,
    val primary: Color,
    val onPrimary: Color,
    val positive: Color,
    val negative: Color,
    val warning: Color,
    val focus: Color,
) {
    /** Token name -> colour, in the same names as `tokens.json` (used by the drift and contrast tests). */
    fun byName(): Map<String, Color> = mapOf(
        "ground" to ground, "surface" to surface, "raised" to raised, "control" to control,
        "text" to text, "muted" to muted, "faint" to faint, "hue" to hue, "track" to track,
        "primary" to primary, "onPrimary" to onPrimary,
        "positive" to positive, "negative" to negative, "warning" to warning, "focus" to focus,
    )
}

/** Token set `dark`: true black. */
val NightPalette = ShelfPalette(
    ground = Color(0xFF000000),
    surface = Color(0xFF111111),
    raised = Color(0xFF2A2A2A),
    control = Color(0xFF444444),
    text = Color(0xFFFFFFFF),
    muted = Color(0xFFB4B4B4),
    faint = Color(0xFF949494),
    hue = Color(0xFF7CC4FF),
    track = Color(0xFF2A2A2A),
    primary = Color(0xFFFFFFFF),
    onPrimary = Color(0xFF000000),
    positive = Color(0xFF9FE3B0),
    negative = Color(0xFFFF6B6F),
    warning = Color(0xFFE5A93B),
    focus = Color(0xFF7CC4FF),
)

/** Token set `light`: plain light grey. */
val DayPalette = ShelfPalette(
    ground = Color(0xFFF5F5F4),
    surface = Color(0xFFFFFFFF),
    raised = Color(0xFFE9E9E7),
    control = Color(0xFFC9C9C6),
    text = Color(0xFF0B0B0B),
    muted = Color(0xFF4F4F4D),
    faint = Color(0xFF626260),
    hue = Color(0xFF1769B5),
    track = Color(0xFFE9E9E7),
    primary = Color(0xFF0B0B0B),
    onPrimary = Color(0xFFFFFFFF),
    positive = Color(0xFF1F7A45),
    negative = Color(0xFFC4242A),
    warning = Color(0xFF8A5200),
    focus = Color(0xFF1769B5),
)
