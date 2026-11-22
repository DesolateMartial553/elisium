package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MediaUrlsTest {
    private fun kind(url: String?): MediaUrlKind = classifyMediaUrl(url).kind

    @Test
    fun `instagram posts and reels`() {
        val post = classifyMediaUrl("https://www.instagram.com/p/CmadeUp0001/")
        assertEquals(MediaUrlKind.POST, post.kind)
        assertEquals("instagram", post.site)
        assertEquals("CmadeUp0001", post.shortcode)

        assertEquals(MediaUrlKind.POST, kind("https://instagram.com/tv/CmadeUp0001"))
        assertEquals(MediaUrlKind.REEL, kind("https://m.instagram.com/reel/CmadeUp0002/?igsh=abc"))
        assertEquals("CmadeUp0002", classifyMediaUrl("https://www.instagram.com/reel/CmadeUp0002/?igsh=abc").shortcode)
    }

    @Test
    fun `instagram story links`() {
        val tray = classifyMediaUrl("https://www.instagram.com/stories/example_user/")
        assertEquals(MediaUrlKind.STORIES_USER, tray.kind)
        assertEquals("example_user", tray.username)

        val story = classifyMediaUrl("https://www.instagram.com/stories/example_user/3412345/?utm_source=ig_web")
        assertEquals(MediaUrlKind.STORY_ITEM, story.kind)
        assertEquals("example_user", story.username)
        assertEquals("3412345", story.storyId)

        val highlight = classifyMediaUrl("https://m.instagram.com/stories/highlights/1791234567890/")
        assertEquals(MediaUrlKind.HIGHLIGHT, highlight.kind)
        assertEquals("1791234567890", highlight.highlightId)
        assertNull(highlight.username)
    }

    @Test
    fun `tiktok photo posts`() {
        val photo = classifyMediaUrl("https://www.tiktok.com/@example_user/photo/7300000000000000001?_t=abc")
        assertEquals(MediaUrlKind.TIKTOK_PHOTO, photo.kind)
        assertEquals("tiktok", photo.site)
        assertEquals("example_user", photo.username)
        assertEquals("7300000000000000001", photo.tiktokId)
    }

    @Test
    fun `video links and profiles are not media posts`() {
        val unknown = listOf(
            "https://www.tiktok.com/@example_user/video/7300000000000000002",
            "https://www.tiktok.com/@example_user",
            "https://www.instagram.com/example_user/",
            "https://www.instagram.com/reels/example_user/",
            "https://www.instagram.com/explore/tags/cats/",
            "https://vm.tiktok.com/ZMabc123/",
            "https://www.instagram.com/stories/highlights/",
            "https://www.instagram.com/stories/example_user/notanid/",
            "https://www.tiktok.com/@example_user/photo/notanid",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        for (url in unknown) assertEquals(url, MediaUrlKind.UNKNOWN, kind(url))
    }

    @Test
    fun `junk input is Unknown and never throws`() {
        for (url in listOf(null, "", "   ", "not a url", "https://", "ftp://example.com/p/x", "instagram.com/p/abc")) {
            assertEquals("$url", MediaUrlKind.UNKNOWN, kind(url))
        }
    }

    @Test
    fun `instagram reel path is still one post`() {
        val reel = classifyMediaUrl("https://www.instagram.com/reel/CmadeUp0003/")
        assertEquals(MediaUrlKind.REEL, reel.kind)
        assertEquals("CmadeUp0003", reel.shortcode)
    }
}
