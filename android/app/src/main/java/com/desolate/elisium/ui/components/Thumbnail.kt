package com.desolate.elisium.ui.components

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Sizes
import com.desolate.elisium.ui.theme.ThumbShape
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val MAX_IMAGE_BYTES = 3 * 1024 * 1024
private val cache = object : LruCache<String, Bitmap>(24) {}

/** Decodes [bytes] sampled down so neither side is much larger than [targetPx] x [targetPx] (pure maths in [sampleSizeFor]). */
private fun decodeSampled(bytes: ByteArray, targetW: Int, targetH: Int): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    val options = BitmapFactory.Options().apply { inSampleSize = sampleSizeFor(bounds.outWidth, bounds.outHeight, targetW, targetH) }
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
}

/** Power-of-two sample size that keeps the decoded picture at least as large as the target. */
fun sampleSizeFor(width: Int, height: Int, targetW: Int, targetH: Int): Int {
    if (width <= 0 || height <= 0 || targetW <= 0 || targetH <= 0) return 1
    var sample = 1
    while (width / (sample * 2) >= targetW && height / (sample * 2) >= targetH) sample *= 2
    return sample
}

private suspend fun fetchBitmap(url: String, targetW: Int, targetH: Int): Bitmap? = withContext(Dispatchers.IO) {
    cache.get(url)?.let { return@withContext it }
    try {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000
            connection.instanceFollowRedirects = true
            if (connection.responseCode !in 200..299) return@withContext null
            val bytes = connection.inputStream.use { input ->
                val out = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                var total = 0
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    total += read
                    if (total > MAX_IMAGE_BYTES) return@withContext null
                    out.write(buffer, 0, read)
                }
                out.toByteArray()
            }
            decodeSampled(bytes, targetW, targetH)?.also { cache.put(url, it) }
        } finally {
            connection.disconnect()
        }
    } catch (_: Exception) {
        null
    }
}

/**
 * The item's picture, [Sizes.THUMB_W_PHONE] x [Sizes.THUMB_H_PHONE] by default, radius 10. Without a picture (none yet, still loading,
 * or it failed) it is a `raised` block with the site name in `faint`, never an icon. Decorative: the row speaks for it.
 */
@Composable
fun Thumbnail(
    url: String?,
    site: String,
    modifier: Modifier = Modifier,
    width: Dp = Sizes.THUMB_W_PHONE.dp,
    height: Dp = Sizes.THUMB_H_PHONE.dp,
) {
    val image: ImageBitmap? by produceState<ImageBitmap?>(initialValue = null, url) {
        value = if (url == null) null else fetchBitmap(url, 208, 118)?.asImageBitmap()
    }
    Box(
        modifier.size(width, height).clip(ThumbShape).background(ElisiumTheme.extras.raised).clearAndSetSemantics { },
        contentAlignment = Alignment.Center,
    ) {
        val shown = image
        if (shown != null) {
            Image(shown, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.size(width, height))
        } else {
            Text(
                site,
                style = MaterialTheme.typography.labelSmall,
                color = ElisiumTheme.extras.faint,
                textAlign = TextAlign.Center,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(horizontal = 6.dp),
            )
        }
    }
}
