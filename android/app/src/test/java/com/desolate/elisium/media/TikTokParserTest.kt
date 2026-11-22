package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TikTokParserTest {
    private fun fixture(name: String): String =
        checkNotNull(javaClass.getResourceAsStream("/media/$name")) { "missing fixture $name" }
            .bufferedReader()
            .use { it.readText() }

    private fun ok(result: MediaResult): MediaPost = when (result) {
        is MediaResult.Ok -> result.posts.single()
        is MediaResult.Failed -> throw AssertionError("expected Ok, got ${result.error}")
    }

    private fun error(result: MediaResult): MediaError = when (result) {
        is MediaResult.Failed -> result.error
        is MediaResult.Ok -> throw AssertionError("expected Failed, got ${result.posts.size} posts")
    }

    @Test
    fun `photo slideshow keeps photo order, ids and the sound`() {
        val post = ok(TikTokParser.parseItem(fixture("tiktok_photo_slideshow.json")))
        assertEquals("tiktok", post.site)
        assertEquals("7300000000000000001", post.id)
        assertEquals("example_user", post.owner)
        assertEquals(1702000000L, post.takenAt)
        assertEquals("A made-up slideshow caption", post.caption)
        assertEquals(2, post.items.size)
        assertEquals(listOf(1, 2), post.items.map { it.index })
        assertEquals(
            listOf("7300000000000000001_1", "7300000000000000001_2"),
            post.items.map { it.mediaId },
        )
        assertEquals("https://cdn.example.com/tiktok/1.jpeg", post.items[0].url)
        assertEquals(1080, post.items[0].width)
        assertEquals(1440, post.items[0].height)
        assertEquals("jpg", post.items[0].ext)
        val music = checkNotNull(post.music)
        assertEquals("https://cdn.example.com/tiktok/sound.mp3", music.url)
        assertEquals("Sound Title", music.title)
        assertEquals("Sound Artist", music.artist)
        assertNull(music.startMs)
        assertNull(music.durationMs)
    }

    @Test
    fun `video item is NoMedia so yt-dlp keeps it`() {
        assertEquals(MediaError.NoMedia, error(TikTokParser.parseItem(fixture("tiktok_video_item.json"))))
    }

    @Test
    fun `malformed and empty responses are typed`() {
        assertEquals(MediaError.Unknown, error(TikTokParser.parseItem("{")))
        assertEquals(MediaError.Unknown, error(TikTokParser.parseItem("")))
        assertEquals(MediaError.Unknown, error(TikTokParser.parseItem(null)))
        assertEquals(MediaError.Unknown, error(TikTokParser.parseItem("{}")))
        assertEquals(MediaError.NoMedia, error(TikTokParser.parseItem("""{"id": "1"}""")))
        assertEquals(
            MediaError.NoMedia,
            error(TikTokParser.parseItem("""{"id": "1", "imagePost": {"images": []}}""")),
        )
    }

    @Test
    fun `photo without a url is skipped and the rest renumber`() {
        val json = """
            {"id": "42", "imagePost": {"images": [
              {"imageURL": {"urlList": []}, "imageWidth": 10, "imageHeight": 10},
              {"imageURL": {"urlList": ["https://cdn.example.com/t/keep.webp"]}, "imageWidth": 20, "imageHeight": 30}
            ]}}
        """.trimIndent()
        val post = ok(TikTokParser.parseItem(json))
        assertEquals(1, post.items.size)
        assertEquals(1, post.items.single().index)
        assertEquals("42_1", post.items.single().mediaId)
        assertEquals("webp", post.items.single().ext)
        assertNull(post.music)
    }

    @Test
    fun `sign-in wall is a typed LoginRequired`() {
        assertEquals(
            MediaError.LoginRequired,
            error(TikTokParser.parseItem("""{"requireLogin": true, "id": "1"}""")),
        )
    }
}
