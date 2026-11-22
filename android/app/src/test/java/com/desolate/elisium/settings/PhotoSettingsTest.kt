package com.desolate.elisium.settings

import com.desolate.elisium.media.MediaRoute
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import com.desolate.elisium.media.routeFor
import org.junit.Assert.assertEquals
import org.junit.Test

class PhotoSettingsTest {
    @Test
    fun `defaults are photos song and video, with the post's snippet`() {
        val s = Settings()
        assertEquals(PhotoMode.PhotosSongVideo, s.photoMode)
        assertEquals(SongLength.Snippet, s.songLength)
        assertEquals(s, s.validated())
    }

    @Test
    fun `stored values round trip and unknown text falls back to the default`() {
        for (mode in PhotoMode.entries) assertEquals(mode, PhotoMode.fromStored(mode.storedValue))
        for (length in SongLength.entries) assertEquals(length, SongLength.fromStored(length.storedValue))
        assertEquals(PhotoMode.PhotosSongVideo, PhotoMode.fromStored(null))
        assertEquals(PhotoMode.PhotosSongVideo, PhotoMode.fromStored("nonsense"))
        assertEquals(SongLength.Snippet, SongLength.fromStored(""))
        assertEquals(listOf("video", "song", "photos"), PhotoMode.entries.map { it.storedValue })
        assertEquals(listOf("snippet", "full"), SongLength.entries.map { it.storedValue })
    }

    @Test
    fun `the routing table per link kind`() {
        val table = listOf(
            "https://www.instagram.com/reel/CreelCode1/" to MediaRoute.YTDLP,
            "https://www.instagram.com/p/CpostCode1/" to MediaRoute.YTDLP_THEN_MEDIA,
            "https://www.instagram.com/tv/CpostCode1/" to MediaRoute.YTDLP_THEN_MEDIA,
            "https://www.instagram.com/stories/someone/" to MediaRoute.MEDIA,
            "https://www.instagram.com/stories/highlights/17900000000000001/" to MediaRoute.MEDIA,
            "https://www.instagram.com/stories/someone/3222222222222222201/" to MediaRoute.YTDLP_THEN_MEDIA,
            "https://www.tiktok.com/@dancer/photo/7300000000000000001" to MediaRoute.MEDIA,
            "https://www.tiktok.com/@dancer/video/7300000000000000002" to MediaRoute.YTDLP,
            "https://vm.tiktok.com/ZMabc/" to MediaRoute.YTDLP,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ" to MediaRoute.YTDLP,
            "https://example.org/x" to MediaRoute.YTDLP,
            "not a url" to MediaRoute.YTDLP,
        )
        for ((url, route) in table) assertEquals(url, route, routeFor(url))
        assertEquals(MediaRoute.YTDLP, routeFor(null))
    }
}
