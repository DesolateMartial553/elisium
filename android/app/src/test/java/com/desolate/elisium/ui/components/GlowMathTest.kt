package com.desolate.elisium.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test

class GlowMathTest {
    @Test fun fractionClampsAndHandlesUnknown() {
        assertEquals(0f, GlowMath.fraction(null as Float?), 0f)
        assertEquals(0f, GlowMath.fraction(null as Int?), 0f)
        assertEquals(0f, GlowMath.fraction(Float.NaN), 0f)
        assertEquals(0f, GlowMath.fraction(-5f), 0f)
        assertEquals(1f, GlowMath.fraction(250f), 0f)
        assertEquals(1f, GlowMath.fraction(Float.POSITIVE_INFINITY), 0f)
        assertEquals(0f, GlowMath.fraction(Float.NEGATIVE_INFINITY), 0f)
        assertEquals(0.42f, GlowMath.fraction(42), 0.0001f)
    }

    @Test fun clampPercent() {
        assertEquals(0, GlowMath.clampPercent(null))
        assertEquals(0, GlowMath.clampPercent(Float.NaN))
        assertEquals(0, GlowMath.clampPercent(-3f))
        assertEquals(100, GlowMath.clampPercent(180f))
        assertEquals(43, GlowMath.clampPercent(42.6f))
    }

    @Test fun fillWidth() {
        assertEquals(0f, GlowMath.fillWidth(300f, 0f, 12f), 0f)
        assertEquals(0f, GlowMath.fillWidth(0f, 0.5f, 12f), 0f)
        assertEquals(150f, GlowMath.fillWidth(300f, 0.5f, 12f), 0.001f)
        assertEquals(300f, GlowMath.fillWidth(300f, 1f, 12f), 0.001f)
        assertEquals(300f, GlowMath.fillWidth(300f, 7f, 12f), 0.001f)
        assertEquals(0f, GlowMath.fillWidth(300f, Float.NaN, 12f), 0f)
        // A tiny non-zero fraction keeps a full round end (at least the bar height).
        assertEquals(12f, GlowMath.fillWidth(300f, 0.01f, 12f), 0.001f)
        // Track narrower than the bar is tall: never wider than the track.
        assertEquals(8f, GlowMath.fillWidth(8f, 0.5f, 12f), 0.001f)
    }

    @Test fun capPosition() {
        assertEquals(144f, GlowMath.capCenterX(300f, 0.5f, 12f), 0.001f)
        assertEquals(294f, GlowMath.capCenterX(300f, 1f, 12f), 0.001f)
        assertEquals(6f, GlowMath.capCenterX(300f, 0.01f, 12f), 0.001f)
        assertEquals(6f, GlowMath.capCenterX(300f, Float.NaN, 12f), 0.001f)
        assertEquals(6f, GlowMath.capCenterX(300f, -1f, 12f), 0.001f)
    }
}
