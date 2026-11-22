package com.desolate.elisium.ui.theme

import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.isSpecified
import java.io.File
import kotlin.math.pow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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

private fun tokenRoot(): JsonObject = Json.parseToJsonElement(tokensFile().readText()).jsonObject

internal fun tokenSet(mode: String): Map<String, String> =
    (tokenRoot()[mode] as JsonObject).mapValues { it.value.jsonPrimitive.content }

private fun group(name: String): JsonObject = tokenRoot()[name] as JsonObject

private fun hexToArgb(hex: String): Int = (0xFF000000L or hex.removePrefix("#").toLong(16)).toInt()

private fun luminance(argb: Int): Double {
    fun lin(c: Double) = if (c <= 0.04045) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
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
        Triple("text", "ground", 4.5), Triple("text", "surface", 4.5), Triple("text", "raised", 4.5),
        Triple("muted", "ground", 4.5), Triple("muted", "surface", 4.5), Triple("muted", "raised", 4.5),
        Triple("faint", "ground", 4.5), Triple("faint", "surface", 4.5),
        Triple("negative", "surface", 4.5), Triple("positive", "surface", 4.5), Triple("warning", "surface", 4.5),
        Triple("onPrimary", "primary", 4.5),
        Triple("hue", "surface", 3.0), Triple("hue", "track", 3.0), Triple("focus", "ground", 3.0), Triple("focus", "surface", 3.0),
    )

    private fun checkEqual(mode: String, palette: ShelfPalette) {
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

    @Test fun radiiMatchTokens() {
        val r = group("radius")
        assertEquals(r.getValue("thumb").jsonPrimitive.int, Radius.THUMB)
        assertEquals(r.getValue("row").jsonPrimitive.int, Radius.ROW)
        assertEquals(r.getValue("card").jsonPrimitive.int, Radius.CARD)
        assertEquals(r.getValue("pill").jsonPrimitive.int, Radius.PILL)
    }

    @Test fun sizesAndSpaceMatchTokens() {
        val size = group("size")
        assertEquals(size.getValue("topBarPhone").jsonPrimitive.int, Sizes.TOP_BAR_PHONE)
        assertEquals(size.getValue("controlPhone").jsonPrimitive.int, Sizes.CONTROL_PHONE)
        assertEquals(size.getValue("minTarget").jsonPrimitive.int, Sizes.MIN_TARGET)
        assertEquals(size.getValue("progress").jsonPrimitive.int, Sizes.PROGRESS)
        val thumb = size.getValue("thumbPhone") as JsonArray
        assertEquals(thumb[0].jsonPrimitive.int, Sizes.THUMB_W_PHONE)
        assertEquals(thumb[1].jsonPrimitive.int, Sizes.THUMB_H_PHONE)
        val space = group("space")
        assertEquals(space.getValue("gap").jsonPrimitive.int, Sizes.GAP)
        assertEquals(space.getValue("gutterPhone").jsonPrimitive.int, Sizes.GUTTER_PHONE)
        assertEquals(space.getValue("pad").jsonPrimitive.int, Sizes.PAD)
    }

    @Test fun typeSizesFamilyAndMotionMatchTokens() {
        val type = group("type")
        assertEquals(type.getValue("title").jsonPrimitive.int, TypeSizes.TITLE)
        assertEquals(type.getValue("rowTitle").jsonPrimitive.int, TypeSizes.ROW_TITLE)
        assertEquals(type.getValue("figure").jsonPrimitive.int, TypeSizes.FIGURE)
        assertEquals(type.getValue("body").jsonPrimitive.int, TypeSizes.BODY)
        assertEquals(type.getValue("meta").jsonPrimitive.int, TypeSizes.META)
        assertEquals(type.getValue("small").jsonPrimitive.int, TypeSizes.SMALL)
        assertEquals(type.getValue("minimum").jsonPrimitive.int, TypeSizes.MINIMUM)
        assertEquals("Hanken Grotesk", type.getValue("family").jsonPrimitive.content)
        assertEquals(listOf(400, 600, 700), (type.getValue("weights") as JsonArray).map { (it as JsonPrimitive).int })
        val motion = group("motion")
        assertEquals(motion.getValue("fastMs").jsonPrimitive.int, Motion.FAST_MS)
        assertEquals(motion.getValue("baseMs").jsonPrimitive.int, Motion.BASE_MS)
        assertEquals("cubic-bezier(0.2, 0, 0, 1)", motion.getValue("easing").jsonPrimitive.content)
        assertEquals(listOf(0.2f, 0f, 0f, 1f), Motion.EASE_POINTS)
    }

    private fun checkContrast(mode: String, palette: ShelfPalette) {
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

    private fun checkSchemeMapping(palette: ShelfPalette, dark: Boolean) {
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
        c(s.onPrimary, s.primary, 4.5, "onPrimary/primary")
        c(s.error, s.surface, 4.5, "error/surface")
        // Night shelf is lightness steps only: the three ground tones, and no tint over the surface.
        assertEquals(palette.ground, s.background)
        assertEquals(palette.surface, s.surface)
        assertEquals(palette.raised, s.surfaceContainerHigh)
        assertEquals(androidx.compose.ui.graphics.Color.Transparent, s.surfaceTint)
        // The inverted primary action: white on black at night, black on white by day.
        assertEquals(palette.primary, s.primary)
        assertEquals(palette.onPrimary, s.onPrimary)
        assertEquals(palette.control, s.outline)
    }

    @Test fun nightSchemeMappingIsReadable() = checkSchemeMapping(NightPalette, true)
    @Test fun daySchemeMappingIsReadable() = checkSchemeMapping(DayPalette, false)

    @Test fun nightShelfHasNoVioletAndPrimaryIsInverted() {
        assertEquals(0xFFFFFFFF.toInt(), NightPalette.primary.toArgb())
        assertEquals(0xFF000000.toInt(), NightPalette.onPrimary.toArgb())
        assertEquals(0xFF0B0B0B.toInt(), DayPalette.primary.toArgb())
        for (p in listOf(NightPalette, DayPalette)) {
            for ((name, color) in p.byName()) {
                val argb = color.toArgb()
                val hsb = java.awt.Color.RGBtoHSB((argb shr 16) and 0xFF, (argb shr 8) and 0xFF, argb and 0xFF, null)
                val degrees = hsb[0] * 360f
                // Violet and indigo sit between 250 and 320 degrees of hue; greys (no saturation) are fine.
                assertFalse("$name looks violet ($degrees degrees)", hsb[1] > 0.15f && degrees in 250f..320f)
            }
        }
    }

    @Test fun typographyNeverBelow12sp() {
        for (size in ElisiumTypography.allSizes()) {
            // unspecified sizes (default styles) are fine; every set size must be >= 12
            if (size.isSpecified) assertTrue("size ${size.value}", size.value >= TypeSizes.MINIMUM)
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
