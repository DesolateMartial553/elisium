package com.desolate.elisium.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import com.desolate.elisium.R

/** Inter, bundled in `res/font` (OFL, see `android/OFL-Inter.txt`). */
val InterFamily = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
    Font(R.font.inter_extrabold, FontWeight.ExtraBold),
)

private fun style(size: Int, lineHeight: Int, weight: FontWeight, tracking: Double = 0.0) = TextStyle(
    fontFamily = InterFamily,
    fontSize = size.sp,
    lineHeight = lineHeight.sp,
    fontWeight = weight,
    letterSpacing = tracking.sp,
)

/** DESIGN.md sizes: title 28, section 18, body 15-16, caption 13. Nothing is below 13sp. */
val ElisiumTypography = Typography(
    displaySmall = style(32, 38, FontWeight.ExtraBold, -0.6),
    headlineMedium = style(28, 34, FontWeight.ExtraBold, -0.5),
    headlineSmall = style(24, 30, FontWeight.Bold, -0.3),
    titleLarge = style(20, 26, FontWeight.Bold, -0.2),
    titleMedium = style(18, 24, FontWeight.SemiBold, -0.1),
    titleSmall = style(16, 22, FontWeight.SemiBold),
    bodyLarge = style(16, 24, FontWeight.Normal),
    bodyMedium = style(15, 22, FontWeight.Normal),
    bodySmall = style(13, 18, FontWeight.Normal),
    labelLarge = style(15, 20, FontWeight.SemiBold),
    labelMedium = style(13, 18, FontWeight.Medium),
    labelSmall = style(13, 18, FontWeight.Medium),
)

/** Tabular figures for speeds, sizes and times so numbers do not jitter while they tick. */
val NumericStyle = TextStyle(fontFeatureSettings = "tnum")

/** Every text size in [ElisiumTypography], for the "never below 13" test. */
fun Typography.allSizes(): List<TextUnit> = listOf(
    displayLarge, displayMedium, displaySmall, headlineLarge, headlineMedium, headlineSmall,
    titleLarge, titleMedium, titleSmall, bodyLarge, bodyMedium, bodySmall, labelLarge, labelMedium, labelSmall,
).map { it.fontSize }
