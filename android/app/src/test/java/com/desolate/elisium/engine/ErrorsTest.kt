package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ErrorsTest {
    @Test
    fun `error table`() {
        val cases = listOf(
            Triple("ERROR: Sign in to confirm you're not a bot", "The site wants you to be signed in.", "Import cookies"),
            Triple("ERROR: Video unavailable", "This video is not available.", "Check the link"),
            Triple("ERROR: Private video. Sign in", "This video is not available.", "Check the link"),
            Triple(
                "ERROR: Requested format is not available",
                "That quality isn't offered for this video.",
                "Pick another format",
            ),
            Triple(
                "ERROR: unable to download video data: HTTP Error 403: Forbidden",
                "The site refused the download.",
                "Update yt-dlp, or import cookies",
            ),
            Triple("ERROR: HTTP Error 429: Too Many Requests", "Too many requests.", "Wait, lower concurrency"),
            Triple("ERROR: Unable to download webpage: timed out", "Network problem.", "Retry (auto-retry already ran)"),
            Triple("ERROR: ffmpeg not found. Please install or provide the path", "ffmpeg is missing.", "Install ffmpeg"),
            Triple("something completely unexpected", "Download failed.", "See Details"),
        )
        for ((raw, message, fix) in cases) {
            val info = explain(raw)
            assertEquals(raw, message, info.message)
            assertEquals(raw, fix, info.fix)
            assertTrue(info.code.isNotEmpty())
        }
    }

    @Test
    fun `matching is case insensitive`() {
        assertEquals("The site wants you to be signed in.", explain("sign IN to CONFIRM").message)
        assertEquals("This video is not available.", explain("PRIVATE VIDEO").message)
    }

    @Test
    fun `first match wins`() {
        assertEquals("http_403", explain("ERROR: unable to download video data: HTTP Error 403: Forbidden").code)
    }

    @Test
    fun `empty log falls back`() {
        assertEquals("Download failed.", explain("").message)
        assertEquals("unknown", explain(null).code)
    }
}
