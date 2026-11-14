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

    // -- Instagram / TikTok (brief 8A/8B) -----------------------------------------------
    @Test
    fun `instagram post forms normalise and share one key`() {
        assertEquals(
            "https://instagram.com/p/CabcDEF123/",
            normalizeUrl("https://www.instagram.com/p/CabcDEF123/?igsh=tracking"),
        )
        assertEquals("https://instagram.com/p/CabcDEF123", normalizeUrl("https://m.instagram.com/p/CabcDEF123"))
        val urls = listOf(
            "https://www.instagram.com/p/CabcDEF123/",
            "https://instagram.com/p/CabcDEF123",
            "https://m.instagram.com/p/CabcDEF123/?igsh=tracking",
            "https://www.instagram.com/p/CabcDEF123/?igshid=abc&utm_source=copy_link",
        )
        for (url in urls) assertEquals(url, "instagram:CabcDEF123", videoKey(url))
    }

    @Test
    fun `instagram reel and tv paths carry the shortcode key`() {
        assertEquals("instagram:CabcDEF123", videoKey("https://www.instagram.com/reel/CabcDEF123/"))
        assertEquals("instagram:CabcDEF123", videoKey("https://www.instagram.com/tv/CabcDEF123/?igsh=abc"))
        assertEquals("https://instagram.com/reel/CabcDEF123/", normalizeUrl("https://www.instagram.com/reel/CabcDEF123/?igsh=abc"))
    }

    @Test
    fun `instagram keeps img_index and drops share junk`() {
        assertEquals(
            "https://instagram.com/p/CabcDEF123/?img_index=2",
            normalizeUrl("https://www.instagram.com/p/CabcDEF123/?img_index=2&igsh=abc&igshid=x&utm_medium=social"),
        )
    }

    @Test
    fun `instagram story key needs an id`() {
        assertEquals("instagram:story:someone:3412345", videoKey("https://www.instagram.com/stories/someone/3412345/"))
        assertNull(videoKey("https://www.instagram.com/stories/someone/"))
        assertNull(videoKey("https://www.instagram.com/stories/highlights/1791234567890/"))
        assertNull(videoKey("https://www.instagram.com/stories/someone/notanid/"))
    }

    @Test
    fun `instagram profile has no video key`() {
        assertNull(videoKey("https://www.instagram.com/someone/"))
        assertNull(videoKey("https://www.instagram.com/explore/tags/cats/"))
    }

    @Test
    fun `tiktok video forms normalise and share one key`() {
        val urls = listOf(
            "https://www.tiktok.com/@tiktok/video/7106594312292453675",
            "https://m.tiktok.com/@tiktok/video/7106594312292453675?_t=abc&_r=1",
            "https://tiktok.com/@tiktok/video/7106594312292453675?is_from_webapp=1&sender_device=pc&utm_source=copy",
        )
        for (url in urls) {
            assertEquals(url, "https://tiktok.com/@tiktok/video/7106594312292453675", normalizeUrl(url))
            assertEquals(url, "tiktok:7106594312292453675", videoKey(url))
        }
    }

    @Test
    fun `tiktok share parameters are all dropped`() {
        val junk = listOf(
            "_t=1", "_r=2", "is_from_webapp=1", "sender_device=pc", "sender_web_id=w", "share_app_id=a",
            "share_link_id=l", "share_item_id=i", "source=h5_m", "checksum=c", "refer=embed", "region=GB",
            "lang=en", "u_code=u", "timestamp=t", "user_id=1", "tt_from=copy",
        )
        assertEquals(
            "https://tiktok.com/@user/video/7106594312292453675",
            normalizeUrl("https://www.tiktok.com/@user/video/7106594312292453675?" + junk.joinToString("&")),
        )
    }

    @Test
    fun `tiktok short link loses junk but has no key`() {
        assertEquals("https://vm.tiktok.com/ZMabc123/", normalizeUrl("https://vm.tiktok.com/ZMabc123/?_t=abc"))
        assertEquals("https://vt.tiktok.com/ZSabc123/", normalizeUrl("https://vt.tiktok.com/ZSabc123/"))
        assertNull(videoKey("https://vm.tiktok.com/ZMabc123/"))
        assertNull(videoKey("https://www.tiktok.com/@user"))
        assertNull(videoKey("https://www.tiktok.com/@user/video/notanid"))
    }

    @Test
    fun `youtube is unchanged by the new site rules`() {
        assertEquals("youtube:$id", videoKey("https://youtu.be/$id"))
        assertNull(videoKey("https://www.youtube.com/@channel"))
    }
}
