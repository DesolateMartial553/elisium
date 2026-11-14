package com.desolate.elisium.ui.theme

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.FiniteAnimationSpec
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween

/** Motion tokens: fast 120, base 220, slow 420 ms, ease-out `cubic-bezier(0.2, 0.8, 0.2, 1)`. */
object Motion {
    const val FAST_MS = 120
    const val BASE_MS = 220
    const val SLOW_MS = 420
    val EaseOut = CubicBezierEasing(0.2f, 0.8f, 0.2f, 1f)

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
