package com.desolate.elisium.ui.theme

import androidx.compose.ui.graphics.toArgb
import java.io.File
import kotlin.math.pow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import androidx.compose.ui.unit.isSpecified
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Finds `design/tokens.json` by walking up from the test working directory (android/app) to the project root. */
internal fun tokensFile(): File {
    var dir: File? = File("").absoluteFile
    while (dir != null) {
        val candidate = File(dir, "design/tokens.json")
        if (candidate.isFile) return candidate
        dir = dir.parentFile
    }
    error("design/tokens.json not found above ${File("").absolutePath}")
}

internal fun tokenSet(mode: String): Map<String, String> {
    val root = Json.parseToJsonElement(tokensFile().readText()).jsonObject
    return (root[mode] as JsonObject).mapValues { it.value.jsonPrimitive.content }
}

private fun hexToArgb(hex: String): Int = (0xFF000000L or hex.removePrefix("#").toLong(16)).toInt()

private fun luminance(argb: Int): Double {
    fun lin(c: Double) = if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
    val r = ((argb shr 16) and 0xFF) / 255.0
    val g = ((argb shr 8) and 0xFF) / 255.0
    val b = (argb and 0xFF) / 255.0
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/** Same formula as `design/contrast_check.py`. */
private fun ratio(a: Int, b: Int): Double {
    val la = luminance(a)
    val lb = luminance(b)
    return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
}

class TokensTest {
    // (foreground, background, minimum): identical to PAIRS in design/contrast_check.py.
    private val pairs = listOf(
        Triple("text", "bg", 4.5), Triple("text", "surface", 4.5), Triple("text", "raised", 4.5),
        Triple("muted", "bg", 4.5), Triple("muted", "surface", 4.5), Triple("muted", "raised", 4.5),
        Triple("accent", "bg", 4.5), Triple("accent", "surface", 4.5), Triple("accent", "raised", 4.5),
        Triple("onAccent", "accent", 4.5),
        Triple("success", "surface", 4.5), Triple("error", "surface", 4.5), Triple("warning", "surface", 4.5),
        Triple("outlineStrong", "bg", 3.0), Triple("outlineStrong", "surface", 3.0), Triple("outlineStrong", "raised", 3.0),
        Triple("glowA", "bg", 3.0), Triple("glowB", "bg", 3.0), Triple("glowC", "bg", 3.0),
    )

    private fun checkEqual(mode: String, palette: AfterglowPalette) {
        val tokens = tokenSet(mode)
        val ours = palette.byName()
        for ((name, hex) in tokens) {
            val color = ours[name] ?: error("token $name ($mode) has no Kotlin colour")
            assertEquals("$mode.$name", hexToArgb(hex), color.toArgb())
        }
        assertEquals("Kotlin palette has colours the token file does not", tokens.keys, ours.keys)
    }

    @Test fun nightMatchesTokens() = checkEqual("dark", NightPalette)
    @Test fun dayMatchesTokens() = checkEqual("light", DayPalette)

    private fun checkContrast(mode: String, palette: AfterglowPalette) {
        val colors = palette.byName()
        for ((fg, bg, need) in pairs) {
            val got = ratio(colors.getValue(fg).toArgb(), colors.getValue(bg).toArgb())
            assertTrue("$mode $fg on $bg is $got, needs $need", got >= need)
        }
    }

    @Test fun nightContrastMeetsLimits() = checkContrast("dark", NightPalette)
    @Test fun dayContrastMeetsLimits() = checkContrast("light", DayPalette)

    @Test fun contrastFormulaMatchesKnownValues() {
        assertEquals(21.0, ratio(0xFF000000.toInt(), 0xFFFFFFFF.toInt()), 0.001)
        assertEquals(1.0, ratio(0xFF123456.toInt(), 0xFF123456.toInt()), 0.001)
    }

    private fun checkSchemeMapping(palette: AfterglowPalette, dark: Boolean) {
        val s = colorSchemeOf(palette, dark)
        fun c(a: androidx.compose.ui.graphics.Color, b: androidx.compose.ui.graphics.Color, need: Double, what: String) {
            val got = ratio(a.toArgb(), b.toArgb())
            assertTrue("$what is $got, needs $need", got >= need)
        }
        c(s.onBackground, s.background, 4.5, "onBackground/background")
        c(s.onSurface, s.surface, 4.5, "onSurface/surface")
        c(s.onSurface, s.surfaceContainerHigh, 4.5, "onSurface/dialog")
        c(s.onSurfaceVariant, s.surface, 4.5, "muted/surface")
        c(s.onSurfaceVariant, s.surfaceVariant, 4.5, "muted/raised")
        c(s.primary, s.background, 4.5, "primary/background")
        c(s.onPrimary, s.primary, 4.5, "onPrimary/primary")
        c(s.error, s.surface, 4.5, "error/surface")
        c(s.onError, s.error, 4.5, "onError/error")
        c(s.outline, s.surface, 3.0, "outline/surface")
        c(s.outline, s.background, 3.0, "outline/background")
        assertEquals("outline is outlineStrong", palette.outlineStrong, s.outline)
        assertEquals(palette.outline, s.outlineVariant)
    }

    @Test fun nightSchemeMappingIsReadable() = checkSchemeMapping(NightPalette, true)
    @Test fun daySchemeMappingIsReadable() = checkSchemeMapping(DayPalette, false)

    @Test fun typographyNeverBelow13sp() {
        for (size in ElisiumTypography.allSizes()) {
            // unspecified sizes (default styles) are fine; every set size must be >= 13
            if (size.isSpecified) assertTrue("size ${size.value}", size.value >= 13f)
        }
    }

    @Test fun reducedMotionRules() {
        assertTrue(isReducedMotion(true, 1f))
        assertTrue(isReducedMotion(false, 0f))
        assertEquals(false, isReducedMotion(false, 1f))
        assertEquals(false, isReducedMotion(false, 0.5f))
    }

    @Test fun appearanceChoosesTheme() {
        assertTrue(useNight(com.desolate.elisium.settings.Appearance.Night, systemDark = false))
        assertEquals(false, useNight(com.desolate.elisium.settings.Appearance.Day, systemDark = true))
        assertTrue(useNight(com.desolate.elisium.settings.Appearance.System, systemDark = true))
        assertEquals(false, useNight(com.desolate.elisium.settings.Appearance.System, systemDark = false))
    }
}
