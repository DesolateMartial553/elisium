package com.desolate.elisium.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Afterglow colour tokens, copied from `design/tokens.json` (a JVM test fails if they drift).
 * Never add a colour here that is not in the token file.
 */
data class AfterglowPalette(
    val bg: Color,
    val surface: Color,
    val raised: Color,
    val outline: Color,
    val text: Color,
    val muted: Color,
    val accent: Color,
    val onAccent: Color,
    val glowA: Color,
    val glowB: Color,
    val glowC: Color,
    val success: Color,
    val error: Color,
    val warning: Color,
    val outlineStrong: Color,
) {
    /** Token name -> colour, in the same names as `tokens.json` (used by the drift and contrast tests). */
    fun byName(): Map<String, Color> = mapOf(
        "bg" to bg, "surface" to surface, "raised" to raised, "outline" to outline,
        "text" to text, "muted" to muted, "accent" to accent, "onAccent" to onAccent,
        "glowA" to glowA, "glowB" to glowB, "glowC" to glowC,
        "success" to success, "error" to error, "warning" to warning, "outlineStrong" to outlineStrong,
    )
}

/** Nightfall (token set `dark`). */
val NightPalette = AfterglowPalette(
    bg = Color(0xFF0E0A1A),
    surface = Color(0xFF171126),
    raised = Color(0xFF211836),
    outline = Color(0xFF3B2E5C),
    text = Color(0xFFF4EFFF),
    muted = Color(0xFFB9ACD9),
    accent = Color(0xFFC4A1FF),
    onAccent = Color(0xFF1A0F33),
    glowA = Color(0xFFB388FF),
    glowB = Color(0xFFFF8FB8),
    glowC = Color(0xFFFFC47E),
    success = Color(0xFF7DE3B2),
    error = Color(0xFFFF8E9B),
    warning = Color(0xFFFFC47E),
    outlineStrong = Color(0xFF8472B5),
)

/** Daybreak (token set `light`). */
val DayPalette = AfterglowPalette(
    bg = Color(0xFFFBF8FF),
    surface = Color(0xFFFFFFFF),
    raised = Color(0xFFF1EAFE),
    outline = Color(0xFFCBBDEA),
    text = Color(0xFF1B1330),
    muted = Color(0xFF5B4D7C),
    accent = Color(0xFF6B3FD4),
    onAccent = Color(0xFFFFFFFF),
    glowA = Color(0xFF7C4DFF),
    glowB = Color(0xFFE0457B),
    glowC = Color(0xFFB3650A),
    success = Color(0xFF0B7A4B),
    error = Color(0xFFB3261E),
    warning = Color(0xFF8A5200),
    outlineStrong = Color(0xFF7A69A8),
)
