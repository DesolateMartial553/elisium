package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Test

class MediaKeysTest {
    private fun item(kind: MediaKind, index: Int, mediaId: String, ext: String = "jpg") =
        MediaItem(kind = kind, url = "https://cdn.example.com/$mediaId.$ext", index = index, mediaId = mediaId, ext = ext)

    @Test
    fun `instagram slide and mix keys`() {
        val post = MediaPost(
            site = "instagram",
            id = "CmadeUp0003",
            items = listOf(item(MediaKind.IMAGE, 1, "3111111111111111201")),
        )
        assertEquals("instagram" to "3111111111111111201", MediaKeys.slide(post, post.items.single()))
        assertEquals("instagram" to "CmadeUp0003_mix", MediaKeys.mix(post))
        assertEquals("instagram 3111111111111111201", MediaKeys.entry(MediaKeys.slide(post, post.items.single())))
    }

    @Test
    fun `tiktok photo and mix keys`() {
        val post = MediaPost(
            site = "tiktok",
            id = "7300000000000000001",
            items = listOf(
                item(MediaKind.IMAGE, 1, "7300000000000000001_1"),
                item(MediaKind.IMAGE, 2, "7300000000000000001_2"),
            ),
        )
        assertEquals("tiktok" to "7300000000000000001_1", MediaKeys.slide(post, post.items[0]))
        assertEquals("tiktok" to "7300000000000000001_2", MediaKeys.slide(post, post.items[1]))
        assertEquals("tiktok" to "7300000000000000001_mix", MediaKeys.mix(post))
    }

    @Test
    fun `a story uses its media id as the slide key`() {
        val post = MediaPost(
            site = "instagram",
            id = "3222222222222222201",
            items = listOf(item(MediaKind.IMAGE, 1, "3222222222222222201")),
        )
        assertEquals("instagram" to "3222222222222222201", MediaKeys.slide(post, post.items.single()))
    }

    @Test
    fun `site is lower-cased in keys`() {
        val post = MediaPost(
            site = "Instagram",
            id = "Cabc",
            items = listOf(item(MediaKind.IMAGE, 1, "1")),
        )
        assertEquals("instagram" to "1", MediaKeys.slide(post, post.items.single()))
        assertEquals("instagram" to "Cabc_mix", MediaKeys.mix(post))
    }
}
