package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class InstagramParserTest {
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
    fun `single image picks the largest candidate`() {
        val post = ok(InstagramParser.parseMediaInfo(fixture("instagram_single_image.json")))
        assertEquals("instagram", post.site)
        assertEquals("CmadeUp0001", post.id)
        assertEquals("example_user", post.owner)
        assertEquals(1701000000L, post.takenAt)
        assertEquals("A made-up caption for tests", post.caption)
        assertNull(post.music)
        assertEquals(1, post.items.size)
        val item = post.items.single()
        assertEquals(MediaKind.IMAGE, item.kind)
        assertEquals("https://cdn.example.com/v/photo-1440.jpg", item.url)
        assertEquals(1440, item.width)
        assertEquals(1800, item.height)
        assertEquals(1, item.index)
        assertEquals("3111111111111111111", item.mediaId)
        assertEquals("jpg", item.ext)
    }

    @Test
    fun `single video picks the largest video version`() {
        val post = ok(InstagramParser.parseMediaInfo(fixture("instagram_single_video.json")))
        val item = post.items.single()
        assertEquals(MediaKind.VIDEO, item.kind)
        assertEquals("https://cdn.example.com/v/video-1080.mp4", item.url)
        assertEquals(1080, item.width)
        assertEquals(1920, item.height)
        assertEquals("mp4", item.ext)
        assertEquals("3111111111111111101", item.mediaId)
    }

    @Test
    fun `mixed carousel keeps slide order and kinds`() {
        val post = ok(InstagramParser.parseMediaInfo(fixture("instagram_carousel_mixed.json")))
        assertEquals("CmadeUp0003", post.id)
        assertEquals(listOf(MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.IMAGE), post.items.map { it.kind })
        assertEquals(listOf(1, 2, 3), post.items.map { it.index })
        assertEquals(
            listOf("3111111111111111201", "3111111111111111202", "3111111111111111203"),
            post.items.map { it.mediaId },
        )
        assertEquals("https://cdn.example.com/c/1.jpg", post.items[0].url)
        assertEquals("https://cdn.example.com/c/2.mp4", post.items[1].url)
        assertEquals("https://cdn.example.com/c/3.jpg", post.items[2].url)
        assertEquals("mp4", post.items[1].ext)
    }

    @Test
    fun `photo post keeps the song snippet`() {
        val post = ok(InstagramParser.parseMediaInfo(fixture("instagram_image_with_music.json")))
        val music = checkNotNull(post.music)
        assertEquals("https://cdn.example.com/audio/example-song.m4a", music.url)
        assertEquals("Example Song", music.title)
        assertEquals("Example Artist", music.artist)
        assertEquals(15400L, music.startMs)
        assertEquals(15000L, music.durationMs)
        assertEquals("m4a", guessExt(music.url, "m4a"))
    }

    @Test
    fun `song without snippet times keeps the full track`() {
        val post = ok(InstagramParser.parseMediaInfo(fixture("instagram_image_with_music_no_snippet.json")))
        val music = checkNotNull(post.music)
        assertEquals("https://cdn.example.com/audio/full-track.m4a", music.url)
        assertEquals("Full Track", music.title)
        assertEquals("Example Artist", music.artist)
        assertNull(music.startMs)
        assertNull(music.durationMs)
    }

    @Test
    fun `stories tray returns one post per story with its music sticker`() {
        val result = InstagramParser.parseStoriesTray(fixture("instagram_stories_tray.json"))
        val posts = (result as? MediaResult.Ok)?.posts ?: throw AssertionError("expected Ok, got $result")
        assertEquals(2, posts.size)
        assertEquals(listOf("3222222222222222201", "3222222222222222202"), posts.map { it.id })
        assertTrue(posts.all { it.site == "instagram" })
        assertTrue(posts.all { it.owner == "example_user" })
        assertEquals(MediaKind.IMAGE, posts[0].items.single().kind)
        assertEquals(MediaKind.VIDEO, posts[1].items.single().kind)
        assertEquals(1701000500L, posts[0].takenAt)
        val music = checkNotNull(posts[0].music)
        assertEquals("https://cdn.example.com/audio/story-song.m4a", music.url)
        assertEquals("Story Song", music.title)
        assertEquals("Example Artist", music.artist)
        assertEquals(5000L, music.startMs)
        assertEquals(15000L, music.durationMs)
        assertNull(posts[1].music)
    }

    @Test
    fun `stories tray in a reels map is accepted`() {
        val json = """
            {"reels": {"1": {"user": {"username": "example_user"}, "items": [
              {"pk": 4001, "media_type": 1,
               "image_versions2": {"candidates": [{"url": "https://cdn.example.com/s.jpg", "width": 1080, "height": 1920}]}}
            ]}}}
        """.trimIndent()
        val result = InstagramParser.parseStoriesTray(json)
        val posts = (result as? MediaResult.Ok)?.posts ?: throw AssertionError("expected Ok, got $result")
        assertEquals(1, posts.size)
        assertEquals("4001", posts.single().id)
    }

    @Test
    fun `malformed json is a typed Unknown`() {
        assertEquals(MediaError.Unknown, error(InstagramParser.parseMediaInfo(fixture("instagram_malformed.json"))))
        assertEquals(MediaError.Unknown, error(InstagramParser.parseMediaInfo("")))
        assertEquals(MediaError.Unknown, error(InstagramParser.parseMediaInfo(null)))
        assertEquals(MediaError.Unknown, error(InstagramParser.parseMediaInfo("[1, 2, 3]")))
    }

    @Test
    fun `empty response is a typed NoMedia`() {
        assertEquals(MediaError.NoMedia, error(InstagramParser.parseMediaInfo(fixture("instagram_empty.json"))))
        assertEquals(MediaError.NoMedia, error(InstagramParser.parseMediaInfo("""{"items": []}""")))
        assertEquals(MediaError.NoMedia, error(InstagramParser.parseStoriesTray("""{"status": "ok"}""")))
    }

    @Test
    fun `sign-in wall is a typed LoginRequired`() {
        val json = fixture("instagram_login_required.json")
        assertEquals(MediaError.LoginRequired, error(InstagramParser.parseMediaInfo(json)))
        assertEquals(MediaError.LoginRequired, error(InstagramParser.parseStoriesTray(json)))
    }

    @Test
    fun `carousel with no slides is NoMedia`() {
        val json = """{"items": [{"pk": 1, "code": "Cabc", "media_type": 8}]}"""
        assertEquals(MediaError.NoMedia, error(InstagramParser.parseMediaInfo(json)))
    }

    @Test
    fun `slides without an identity are skipped and renumbered`() {
        val json = """
            {"items": [{"pk": 99, "code": "Cabc", "media_type": 8, "carousel_media": [
              {"media_type": 1, "image_versions2": {"candidates": [{"url": "https://cdn.example.com/no-id.jpg"}]}},
              {"pk": 101, "media_type": 1, "image_versions2": {"candidates": [{"url": "https://cdn.example.com/one.jpg"}]}},
              {"pk": 102, "media_type": 1, "image_versions2": {"candidates": [{"url": "https://cdn.example.com/two.jpg"}]}}
            ]}]}
        """.trimIndent()
        val post = ok(InstagramParser.parseMediaInfo(json))
        assertEquals(listOf("101", "102"), post.items.map { it.mediaId })
        assertEquals(listOf(1, 2), post.items.map { it.index })
    }

    @Test
    fun `unknown media type falls back to the fields present`() {
        val json = """
            {"items": [{"pk": 1, "code": "Cabc", "media_type": 7,
              "video_versions": [{"url": "https://cdn.example.com/v.mp4", "width": 10, "height": 20}]}]}
        """.trimIndent()
        val post = ok(InstagramParser.parseMediaInfo(json))
        assertEquals(MediaKind.VIDEO, post.items.single().kind)
    }

    @Test
    fun `music without a download url is ignored, not fatal`() {
        val json = """
            {"items": [{"pk": 1, "code": "Cabc", "media_type": 1,
              "image_versions2": {"candidates": [{"url": "https://cdn.example.com/a.jpg"}]},
              "music_metadata": {"music_info": {"music_asset_info": {"title": "No URL"}}}}]}
        """.trimIndent()
        val post = ok(InstagramParser.parseMediaInfo(json))
        assertNull(post.music)
    }

    @Test
    fun `wrongly typed fields never crash`() {
        val json = """
            {"items": [{"pk": "notanumber", "code": "Cabc", "media_type": "one",
              "taken_at": "yesterday", "caption": "not an object",
              "image_versions2": {"candidates": [{"url": "https://cdn.example.com/x.webp"}]},
              "user": [1, 2]}]}
        """.trimIndent()
        val post = ok(InstagramParser.parseMediaInfo(json))
        assertEquals("notanumber", post.items.single().mediaId)
        assertNull(post.takenAt)
        assertNull(post.caption)
        assertNull(post.owner)
        assertEquals("webp", post.items.single().ext)
    }
}
