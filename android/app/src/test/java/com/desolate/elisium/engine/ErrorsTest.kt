package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
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
                "Update yt-dlp in Settings, or sign in",
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
            // Brief 9B: the fix is one tap inside the app, not a file copied from a computer.
            assertEquals(raw, "Sign in to Instagram in Settings > Accounts", info.fix)
        }
    }

    @Test
    fun `instagram rows come before the generic 429 and network rows`() {
        assertEquals("rate_limited", explain("Please wait a few minutes. HTTP Error 429").code)
        assertEquals("login_required", explain("You need to log in to access this content").code)
        // A plain HTTP 429 on another site is still the generic row.
        assertEquals("http_429", explain("ERROR: HTTP Error 429: Too Many Requests").code)
    }

    // -- brief 9A: context-aware explain ------------------------------------------------
    private val igPost = "https://www.instagram.com/p/CabcDEF123/"
    private val ytUrl = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    private val loginRaw =
        "ERROR: You need to log in to access this content. Use --cookies-from-browser or --cookies"

    @Test
    fun `http 401 maps to its own row`() {
        val info = explain("ERROR: unable to download video data: HTTP Error 401: Unauthorized")
        assertEquals("http_401", info.code)
        assertEquals("The site refused to let Elisium in.", info.message)
        assertEquals("Sign in, then try again", info.fix)
        assertEquals("http_403", explain("ERROR: HTTP Error 403: Forbidden").code)
        assertEquals("http_429", explain("ERROR: HTTP Error 429: Too Many Requests").code)
    }

    @Test
    fun `a post with no video maps to no media`() {
        for (raw in listOf(
            // raise_no_formats("There is no video in this post", expected = true)
            "ERROR: [Instagram] CabcDEF123: There is no video in this post",
            // the empty Polaris response, verbatim from extractor/instagram.py
            "ERROR: Instagram sent an empty media response. Check if this post is accessible in your " +
                "browser without being logged-in. If it is not, then use --cookies-from-browser or " +
                "--cookies for the authentication.",
        )) {
            val info = explain(raw)
            assertEquals(raw, "no_media", info.code)
            assertEquals(raw, "This post has no video to download.", info.message)
            assertEquals(raw, "Check the link", info.fix)
        }
        // The empty-response text mentions cookies but is not a sign-in failure.
        assertEquals(
            "no_media",
            explain("ERROR: Instagram sent an empty media response. ... use --cookies-from-browser", igPost, true).code,
        )
        assertEquals("session_expired", explain(loginRaw, igPost, true).code)
    }

    @Test
    fun `login required is generic for other sites`() {
        val info = explain(loginRaw, ytUrl)
        assertEquals("login_required", info.code)
        assertEquals("The site wants you to be signed in.", info.message)
        assertEquals("Sign in to Instagram in Settings > Accounts", info.fix)
        // An Instagram URL, and no URL at all, keep the Instagram wording.
        assertEquals("Instagram needs you signed in.", explain(loginRaw, igPost).message)
        assertEquals("Instagram needs you signed in.", explain(loginRaw).message)
        assertEquals("Instagram needs you signed in.", explain(loginRaw, null).message)
    }

    @Test
    fun `rate limited is generic for other sites`() {
        val raw = "ERROR: Please wait a few minutes before you try again."
        val other = explain(raw, ytUrl)
        assertEquals("rate_limited", other.code)
        assertEquals("The site is limiting requests. Wait a few minutes and try again.", other.message)
        assertEquals("Wait a few minutes and try again", other.fix)
        assertEquals(
            "Instagram is limiting requests. Wait a few minutes and try again.",
            explain(raw, igPost).message,
        )
        assertEquals(
            "Instagram is limiting requests. Wait a few minutes and try again.",
            explain(raw).message,
        )
    }

    @Test
    fun `expired session needs cookies and instagram`() {
        val expired = explain(loginRaw, igPost, true)
        assertEquals("session_expired", expired.code)
        assertEquals("Your Instagram sign-in has expired.", expired.message)
        assertEquals("Sign in to Instagram in Settings > Accounts", expired.fix)
        // No cookies configured: still a plain sign-in failure.
        assertEquals("login_required", explain(loginRaw, igPost, false).code)
        assertEquals("login_required", explain(loginRaw, igPost).code)
        // No URL: an Instagram-only row, so cookies still mean an expired session.
        assertEquals("session_expired", explain(loginRaw, hasCookies = true).code)
        // Another site never gets "your Instagram sign-in has expired".
        val other = explain(loginRaw, ytUrl, true)
        assertEquals("login_required", other.code)
        assertFalse(other.message.contains("Instagram"))
        assertNotEquals("session_expired", other.code)
    }

    @Test
    fun `default arguments keep the old behaviour`() {
        for (raw in listOf(loginRaw, "HTTP Error 401", "HTTP Error 403", "")) {
            assertEquals(raw, explain(raw), explain(raw, null, false))
            assertEquals(raw, explain(raw), explain(raw, url = null, hasCookies = false))
        }
    }
}
