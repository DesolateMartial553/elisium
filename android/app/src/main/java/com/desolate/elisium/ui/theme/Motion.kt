package com.desolate.elisium.ui.theme

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween

/** Motion tokens: fast 120, base 200 ms, ease-out `cubic-bezier(0.2, 0, 0, 1)`. No looping animation anywhere. */
object Motion {
    const val FAST_MS = 120
    const val BASE_MS = 200
    /** The easing curve control points: cubic-bezier(0.2, 0, 0, 1). */
    val EASE_POINTS = listOf(0.2f, 0f, 0f, 1f)
    val EaseOut = CubicBezierEasing(EASE_POINTS[0], EASE_POINTS[1], EASE_POINTS[2], EASE_POINTS[3])

    /** A tween with the token easing, or an instant change when motion is reduced. */
    fun <T> spec(durationMs: Int, reduced: Boolean): FiniteAnimationSpec<T> =
        if (reduced) snap() else tween(durationMs, easing = EaseOut)
}

/**
 * Motion is off when the user chose "Reduce motion" in Settings or the system animation scale is 0
 * ("remove animations").
 */
fun isReducedMotion(settingOn: Boolean, animatorDurationScale: Float): Boolean =
    settingOn || animatorDurationScale == 0f
