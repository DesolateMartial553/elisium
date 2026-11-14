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

    // -- Instagram / TikTok (brief 8A/8B) -------------------------------------------------
    @Test
    fun `instagram sign in maps to login required`() {
        val raw = "ERROR: [Instagram] someone: You need to log in to access this content. Use --cookies-from-browser or --cookies."
        val info = explain(raw)
        assertEquals("Instagram needs you signed in.", info.message)
        assertEquals("login_required", info.code)
        assertTrue(info.fix.contains("Settings > Accounts"))
        assertEquals("login_required", explain("You must be logged in to view this content").code)
    }

    @Test
    fun `instagram pacing maps to rate limited`() {
        val info = explain("ERROR: [Instagram] Please wait a few minutes before you try again.")
        assertEquals("Instagram is limiting requests. Wait a few minutes and try again.", info.message)
        assertEquals("rate_limited", info.code)
        assertEquals("Wait a few minutes and try again", info.fix)
    }

    @Test
    fun `unreadable cookies map to cookies unreadable`() {
        for (raw in listOf(
            "ERROR: could not find firefox cookies database in /home/x",
            "ERROR: Failed to decrypt with DPAPI",
            "ERROR: does not look like a Netscape format cookies file",
        )) {
            val info = explain(raw)
            assertEquals(raw, "cookies_unreadable", info.code)
            assertTrue(raw, info.fix.contains("Settings > Accounts"))
        }
    }

    @Test
    fun `instagram rows come before the generic 429 and network rows`() {
        assertEquals("rate_limited", explain("Please wait a few minutes. HTTP Error 429").code)
        assertEquals("login_required", explain("You need to log in to access this content").code)
        // A plain HTTP 429 on another site is still the generic row.
        assertEquals("http_429", explain("ERROR: HTTP Error 429: Too Many Requests").code)
    }
}
