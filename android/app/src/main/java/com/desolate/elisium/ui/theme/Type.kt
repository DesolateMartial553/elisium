package com.desolate.elisium.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import com.desolate.elisium.R

/** Hanken Grotesk 400/600/700, bundled in `res/font` (SIL OFL, text in `res/raw/hanken_grotesk_ofl.txt`). */
val HankenFamily = FontFamily(
    Font(R.font.hanken_grotesk_regular, FontWeight.Normal),
    Font(R.font.hanken_grotesk_semibold, FontWeight.SemiBold),
    Font(R.font.hanken_grotesk_bold, FontWeight.Bold),
)

private fun style(size: Int, lineHeight: Int, weight: FontWeight) = TextStyle(
    fontFamily = HankenFamily,
    fontSize = size.sp,
    lineHeight = lineHeight.sp,
    fontWeight = weight,
)

/**
 * DESIGN.md sizes: screen title 20/700, row title 15/600, big figure 24/600, body 14, meta 13, small 12.
 * Nothing is below 12sp. Every slot Material may reach is mapped to one of those sizes.
 */
val ElisiumTypography = Typography(
    displayLarge = style(TypeSizes.FIGURE, 30, FontWeight.SemiBold),
    displayMedium = style(TypeSizes.FIGURE, 30, FontWeight.SemiBold),
    displaySmall = style(TypeSizes.FIGURE, 30, FontWeight.SemiBold),
    headlineLarge = style(TypeSizes.TITLE, 26, FontWeight.Bold),
    headlineMedium = style(TypeSizes.TITLE, 26, FontWeight.Bold),
    headlineSmall = style(TypeSizes.FIGURE, 30, FontWeight.SemiBold),
    titleLarge = style(TypeSizes.TITLE, 26, FontWeight.Bold),
    titleMedium = style(TypeSizes.ROW_TITLE, 20, FontWeight.SemiBold),
    titleSmall = style(TypeSizes.BODY, 20, FontWeight.SemiBold),
    bodyLarge = style(TypeSizes.BODY, 20, FontWeight.Normal),
    bodyMedium = style(TypeSizes.BODY, 20, FontWeight.Normal),
    bodySmall = style(TypeSizes.META, 18, FontWeight.Normal),
    labelLarge = style(TypeSizes.BODY, 20, FontWeight.SemiBold),
    labelMedium = style(TypeSizes.META, 18, FontWeight.SemiBold),
    labelSmall = style(TypeSizes.SMALL, 16, FontWeight.Normal),
)

/** Tabular figures for percent, speed, size, time left and counts so numbers do not jitter while they tick. */
val NumericStyle = TextStyle(fontFeatureSettings = "tnum")

/** Every text size in [ElisiumTypography], for the "never below 12" test. */
fun Typography.allSizes(): List<TextUnit> = listOf(
    displayLarge, displayMedium, displaySmall, headlineLarge, headlineMedium, headlineSmall,
    titleLarge, titleMedium, titleSmall, bodyLarge, bodyMedium, bodySmall, labelLarge, labelMedium, labelSmall,
).map { it.fontSize }
