package com.desolate.elisium.ui.components

import android.content.res.Configuration
import androidx.compose.ui.tooling.preview.Preview

/** Night, Day and Night at font scale 2.0: the three previews the owner flips through in Android Studio. */
@Preview(name = "Night", showBackground = true, backgroundColor = 0xFF0E0A1A, uiMode = Configuration.UI_MODE_NIGHT_YES)
@Preview(name = "Day", showBackground = true, backgroundColor = 0xFFFBF8FF, uiMode = Configuration.UI_MODE_NIGHT_NO)
@Preview(name = "Night, font 2.0", showBackground = true, backgroundColor = 0xFF0E0A1A, uiMode = Configuration.UI_MODE_NIGHT_YES, fontScale = 2f)
annotation class AfterglowPreviews
