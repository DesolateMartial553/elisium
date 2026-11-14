package com.desolate.elisium.ui.components

import android.os.Build
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlurEffect
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion

/** Look of a [GlowProgress]; the state is always also written as a word elsewhere (never colour alone). */
enum class GlowState { Active, Paused, Done, Failed }

private val GlowPad = 8.dp

/**
 * Thick rounded bar filled with the glow gradient (glowA -> glowB -> glowC) and a glowing leading cap.
 * Paused is a muted gradient without glow, Done is solid success, Failed is solid error.
 * [fraction] null means unknown: a short segment slides along the track (or sits still when motion is reduced).
 * Semantics: "N percent" range info is set here; rows that merge their own semantics override it.
 * Compile-verified only.
 */
@Composable
fun GlowProgress(
    fraction: Float?,
    modifier: Modifier = Modifier,
    state: GlowState = GlowState.Active,
    barHeight: androidx.compose.ui.unit.Dp = 12.dp,
    percentDescription: String? = null,
) {
    val extras = ElisiumTheme.extras
    val reduced = extras.reducedMotion
    val known = fraction != null && !fraction.isNaN()
    val target = GlowMath.fraction(if (known) fraction!! * 100f else null)
    val shown by animateFloatAsState(target, Motion.spec(Motion.BASE_MS, reduced), label = "glowFill")

    val active = state == GlowState.Active
    // Loops only run while they are needed: nothing animates for Done/Failed/Paused or with reduced motion.
    val breathing = if (active && !reduced) breathingLoop() else 1f
    val slide = if (!known && !reduced) slideLoop() else 0f

    val semanticsMod = if (known) {
        Modifier.semantics {
            progressBarRangeInfo = ProgressBarRangeInfo(target, 0f..1f)
            if (percentDescription != null) contentDescription = percentDescription
        }
    } else {
        Modifier
    }

    val useBlur = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    val colors = when (state) {
        GlowState.Active -> extras.glowColors
        GlowState.Paused -> extras.glowColors.map { it.copy(alpha = 0.45f) }
        GlowState.Done -> listOf(extras.success, extras.success)
        GlowState.Failed -> listOf(extras.error, extras.error)
    }
    val capColor = when (state) {
        GlowState.Active -> extras.glowC
        else -> Color.Transparent
    }

    Box(modifier = modifier.fillMaxWidth().height(barHeight + GlowPad * 2).then(semanticsMod)) {
        // Blurred cap glow sits on its own layer (API 31+); older versions get layered alpha circles below.
        if (active && useBlur) {
            Canvas(
                Modifier.fillMaxWidth().height(barHeight + GlowPad * 2)
                    .graphicsLayer {
                        renderEffect = BlurEffect(10.dp.toPx(), 10.dp.toPx(), TileMode.Decal)
                        alpha = breathing
                    },
            ) {
                val h = barHeight.toPx()
                val cx = if (known) GlowMath.capCenterX(size.width, shown, h) else size.width * 0.5f
                if (!known || shown > 0f) {
                    drawCircle(capColor.copy(alpha = 0.85f), radius = h * 0.9f, center = Offset(cx, size.height / 2f))
                }
            }
        }
        Canvas(Modifier.fillMaxWidth().height(barHeight + GlowPad * 2)) {
            val h = barHeight.toPx()
            val top = (size.height - h) / 2f
            val radius = CornerRadius(h / 2f, h / 2f)
            // Track
            drawRoundRect(extras.outline.copy(alpha = 0.55f), Offset(0f, top), Size(size.width, h), radius)

            if (known) {
                val w = GlowMath.fillWidth(size.width, shown, h)
                if (w > 0f) {
                    val brush = Brush.horizontalGradient(colors, startX = 0f, endX = w.coerceAtLeast(1f))
                    drawRoundRect(brush, Offset(0f, top), Size(w, h), radius)
                    if (active && !useBlur) {
                        val cx = GlowMath.capCenterX(size.width, shown, h)
                        val layers = 4
                        for (i in layers downTo 1) {
                            drawCircle(
                                capColor.copy(alpha = 0.10f * breathing),
                                radius = h / 2f + i * 2.dp.toPx(),
                                center = Offset(cx, size.height / 2f),
                            )
                        }
                    }
                    if (active) {
                        val cx = GlowMath.capCenterX(size.width, shown, h)
                        drawCircle(Color.White.copy(alpha = 0.55f * breathing), radius = h * 0.28f, center = Offset(cx, size.height / 2f))
                    }
                }
            } else {
                val seg = size.width * 0.3f
                val start = if (reduced) 0f else (size.width - seg) * slide
                val brush = Brush.horizontalGradient(colors, startX = start, endX = start + seg)
                drawRoundRect(brush, Offset(start, top), Size(seg, h), radius)
            }
        }
    }
}

@Composable
private fun breathingLoop(): Float {
    val t = rememberInfiniteTransition(label = "glow")
    val v by t.animateFloat(
        initialValue = 0.65f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Reverse),
        label = "breathe",
    )
    return v
}

@Composable
private fun slideLoop(): Float {
    val t = rememberInfiniteTransition(label = "slide")
    val v by t.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1500, easing = LinearEasing), RepeatMode.Restart),
        label = "slide",
    )
    return v
}

@AfterglowPreviews
@Composable
private fun GlowProgressPreview() {
    ElisiumTheme {
        Surface(color = androidx.compose.material3.MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp)) {
                GlowProgress(0.42f)
                GlowProgress(0.8f, state = GlowState.Paused)
                GlowProgress(1f, state = GlowState.Done)
                GlowProgress(0.3f, state = GlowState.Failed)
                GlowProgress(null)
            }
        }
    }
}
