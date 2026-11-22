package com.desolate.elisium.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/** Radii and sizes from `design/nightshelf/tokens.json` (a JVM test reads the file and fails if these drift). */
object Radius {
    const val THUMB = 10
    const val ROW = 16
    const val CARD = 14
    const val PILL = 999
}

object Sizes {
    const val TOP_BAR_PHONE = 56
    const val CONTROL_PHONE = 44
    const val MIN_TARGET = 44
    const val CHIP = 36
    const val THUMB_W_PHONE = 104
    const val THUMB_H_PHONE = 59
    const val PROGRESS = 4
    const val GUTTER_PHONE = 16
    const val GAP = 8
    const val PAD = 16
}

/** Type sizes in sp (tokens `type`). Nothing is smaller than [MINIMUM]. */
object TypeSizes {
    const val TITLE = 20
    const val ROW_TITLE = 15
    const val FIGURE = 24
    const val BODY = 14
    const val META = 13
    const val SMALL = 12
    const val MINIMUM = 12
}

val ThumbShape = RoundedCornerShape(Radius.THUMB.dp)
val RowShape = RoundedCornerShape(Radius.ROW.dp)
val CardShape = RoundedCornerShape(Radius.CARD.dp)
val PillShape = RoundedCornerShape(50)

val ElisiumShapes = Shapes(
    extraSmall = ThumbShape,
    small = ThumbShape,
    medium = CardShape,
    large = RowShape,
    extraLarge = RowShape,
)
