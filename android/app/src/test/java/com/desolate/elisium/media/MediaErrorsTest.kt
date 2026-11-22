package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Test

/** Every media failure, in the desktop `errors.py` words. */
class MediaErrorsTest {
    private val ig = "https://www.instagram.com/p/AbC/"
    private val story = "https://www.instagram.com/stories/someone/3222222222222222201/"
    private val tray = "https://www.instagram.com/stories/someone/"
    private val tt = "https://www.tiktok.com/@u/photo/73"

    @Test
    fun `login wall`() {
        val e = mediaErrorInfo(MediaFailure.LOGIN_REQUIRED, ig, hasCookies = false)
        assertEquals("login_required", e.code)
        assertEquals("Instagram needs you signed in.", e.message)
        assertEquals("Sign in to Instagram in Settings > Accounts", e.fix)
    }

    @Test
    fun `login wall with cookies is an expired sign-in`() {
        val e = mediaErrorInfo(MediaFailure.LOGIN_REQUIRED, story, hasCookies = true)
        assertEquals("session_expired", e.code)
        assertEquals("Your Instagram sign-in has expired.", e.message)
    }

    @Test
    fun `tiktok never names instagram`() {
        val e = mediaErrorInfo(MediaFailure.LOGIN_REQUIRED, tt, hasCookies = true)
        assertEquals("login_required", e.code)
        assertEquals("The site wants you to be signed in.", e.message)
        val r = mediaErrorInfo(MediaFailure.RATE_LIMITED, tt, hasCookies = false)
        assertEquals("The site is limiting requests. Wait a few minutes and try again.", r.message)
    }

    @Test
    fun `rate limit`() {
        val e = mediaErrorInfo(MediaFailure.RATE_LIMITED, ig, hasCookies = true)
        assertEquals("rate_limited", e.code)
        assertEquals("Instagram is limiting requests. Wait a few minutes and try again.", e.message)
        assertEquals("Wait a few minutes and try again", e.fix)
    }

    @Test
    fun `not found is a gone story on a story link, else not available`() {
        assertEquals("story_expired", mediaErrorInfo(MediaFailure.NOT_FOUND, story, false).code)
        assertEquals("story_expired", mediaErrorInfo(MediaFailure.NOT_FOUND, "https://www.instagram.com/stories/highlights/1/", false).code)
        val e = mediaErrorInfo(MediaFailure.NOT_FOUND, ig, false)
        assertEquals("video_unavailable", e.code)
        assertEquals("This video is not available.", e.message)
    }

    @Test
    fun `expired story words`() {
        val e = mediaErrorInfo(MediaFailure.NO_MEDIA, tray, false)
        assertEquals("story_expired", e.code)
        assertEquals("This story has expired. Stories last 24 hours.", e.message)
        assertEquals("Check the link", e.fix)
    }

    @Test
    fun `an empty non-story result is no_media`() {
        val e = mediaErrorInfo(MediaFailure.NO_MEDIA, ig, false)
        assertEquals("no_media", e.code)
        assertEquals("There are no photos or videos to download here.", e.message)
        assertEquals("no_media", mediaErrorInfo(MediaFailure.NO_MEDIA, tt, false).code)
    }

    @Test
    fun `private account words`() {
        val e = mediaErrorInfo(MediaFailure.PRIVATE, tray, true)
        assertEquals("private_account", e.code)
        assertEquals("This account is private. Follow it in your browser, then sign in here.", e.message)
        assertEquals("Follow the account in your browser, then sign in in Settings > Accounts", e.fix)
    }

    @Test
    fun `network failures are the retried network code`() {
        val e = mediaErrorInfo(MediaFailure.NETWORK, ig, false)
        assertEquals("network", e.code)
        assertEquals("Network problem.", e.message)
    }

    @Test
    fun `anything else is the generic failure`() {
        val e = mediaErrorInfo(MediaFailure.UNKNOWN, ig, false)
        assertEquals("unknown", e.code)
        assertEquals("Download failed.", e.message)
    }
}
