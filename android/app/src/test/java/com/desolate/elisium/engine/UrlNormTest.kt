package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.fail
import org.junit.Test

class UrlNormTest {
    private val id = "dQw4w9WgXcQ"
    private val canonical = "https://www.youtube.com/watch?v=$id"

    @Test
    fun `all youtube forms normalise and share one key`() {
        val urls = listOf(
            "https://youtu.be/$id",
            "https://www.youtube.com/watch?v=$id",
            "http://youtube.com/watch?v=$id",
            "https://m.youtube.com/watch?v=$id",
            "https://music.youtube.com/watch?v=$id",
            "https://www.youtube.com/shorts/$id",
            "https://www.youtube.com/embed/$id",
            "https://www.youtube.com/live/$id",
            "https://youtu.be/$id?si=tracking123",
            "https://www.youtube.com/watch?v=$id&feature=share&pp=abc",
        )
        for (url in urls) {
            assertEquals(url, canonical, normalizeUrl(url))
            assertEquals(url, "youtube:$id", videoKey(url))
        }
    }

    @Test
    fun `tracking params are stripped from a single video`() {
        val url = "https://www.youtube.com/watch?v=$id" +
            "&si=abc&feature=share&pp=xyz&utm_source=newsletter&utm_medium=email" +
            "&list=PL123&index=4"
        assertEquals(canonical, normalizeUrl(url))
    }

    @Test
    fun `start time is kept in normalised form`() {
        assertEquals("$canonical&t=90", normalizeUrl("https://youtu.be/$id?t=90"))
        assertEquals("$canonical&t=1m30s", normalizeUrl("https://www.youtube.com/watch?v=$id&t=1m30s"))
        assertEquals("$canonical&t=45", normalizeUrl("https://www.youtube.com/watch?v=$id&start=45"))
    }

    @Test
    fun `non time t is dropped`() {
        assertEquals(canonical, normalizeUrl("https://youtu.be/$id?t=notatime"))
    }

    @Test
    fun `playlist url keeps list`() {
        assertEquals(
            "https://www.youtube.com/playlist?list=PL123",
            normalizeUrl("https://www.youtube.com/playlist?list=PL123&si=abc&utm_source=x"),
        )
        assertEquals(
            "https://www.youtube.com/playlist?list=PL123&index=2",
            normalizeUrl("https://www.youtube.com/playlist?list=PL123&index=2"),
        )
    }

    @Test
    fun `playlist link has no video key`() {
        assertNull(videoKey("https://www.youtube.com/playlist?list=PL123"))
    }

    @Test
    fun `other sites lowercase scheme and host and strip fragment and utm`() {
        assertEquals(
            "https://example.com/Some/Path?a=1&b=2",
            normalizeUrl("HTTPS://Example.COM/Some/Path?utm_source=x&a=1&b=2#section"),
        )
    }

    @Test
    fun `other sites have no video key`() {
        assertNull(videoKey("https://vimeo.com/12345"))
    }

    @Test
    fun `other sites only drop utm params`() {
        assertEquals(
            "https://example.com/watch?si=keep&feature=keep",
            normalizeUrl("https://example.com/watch?si=keep&feature=keep&utm_source=x"),
        )
    }

    @Test
    fun `invalid input raises IllegalArgumentException`() {
        for (url in listOf("", "   ", "not a url", "https://", "ftp://example.com/x")) {
            try {
                normalizeUrl(url)
                fail("normalizeUrl accepted '$url'")
            } catch (_: IllegalArgumentException) {
            }
            try {
                videoKey(url)
                fail("videoKey accepted '$url'")
            } catch (_: IllegalArgumentException) {
            }
        }
    }

    // Extra cases beyond the Python file, covering the hand-written parser.
    @Test
    fun `default port and userinfo handling matches python`() {
        assertEquals("https://example.com/a", normalizeUrl("https://Example.com:443/a"))
        assertEquals("http://example.com:8080/a", normalizeUrl("http://example.com:8080/a"))
        assertEquals("https://u:p@example.com/a", normalizeUrl("https://u:p@example.com/a"))
        assertEquals("https://example.com", normalizeUrl("https://example.com"))
    }

    @Test
    fun `query values are re-encoded like urlencode`() {
        assertEquals("https://example.com/p?q=a+b&r=%C3%A9", normalizeUrl("https://example.com/p?q=a%20b&r=%C3%A9"))
        assertEquals("https://example.com/p?flag=", normalizeUrl("https://example.com/p?flag"))
    }
}
