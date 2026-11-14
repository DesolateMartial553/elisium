package com.desolate.elisium.ui.components

/** Pure geometry for the glow progress bar, so it can be JVM-tested. All widths are in the same unit (px). */
object GlowMath {
    /** Fraction 0..1 for a percent that may be null, NaN, infinite or outside 0..100 (all become safe values). */
    fun fraction(percent: Float?): Float {
        if (percent == null || percent.isNaN()) return 0f
        return (percent / 100f).coerceIn(0f, 1f)
    }

    fun fraction(percent: Int?): Float = fraction(percent?.toFloat())

    /** Whole percent 0..100 (rounded), 0 for null or NaN. */
    fun clampPercent(percent: Float?): Int {
        if (percent == null || percent.isNaN()) return 0
        return percent.coerceIn(0f, 100f).let { Math.round(it) }
    }

    /**
     * Width of the filled part. Zero at 0%; otherwise never narrower than the bar is tall (so the rounded
     * end stays a full circle) and never wider than the track.
     */
    fun fillWidth(trackWidth: Float, fraction: Float, barHeight: Float): Float {
        if (trackWidth <= 0f) return 0f
        val f = if (fraction.isNaN()) 0f else fraction.coerceIn(0f, 1f)
        if (f <= 0f) return 0f
        return (trackWidth * f).coerceAtLeast(barHeight.coerceAtMost(trackWidth)).coerceAtMost(trackWidth)
    }

    /** Centre x of the glowing cap: half a bar-height inside the leading edge of the fill. */
    fun capCenterX(trackWidth: Float, fraction: Float, barHeight: Float): Float {
        val fill = fillWidth(trackWidth, fraction, barHeight)
        return (fill - barHeight / 2f).coerceAtLeast(barHeight / 2f).coerceAtMost(trackWidth.coerceAtLeast(barHeight / 2f))
    }
}
