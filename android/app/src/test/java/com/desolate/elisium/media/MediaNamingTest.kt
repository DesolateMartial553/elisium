package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaNamingTest {
    private val post = MediaPost(
        site = "instagram", id = "CMus789rst", owner = "dj_north", takenAt = 1699000000L,
        items = listOf(MediaItem(MediaKind.IMAGE, "https://x/1.jpg", index = 2, mediaId = "3302000000000000009", ext = "jpg")),
    )

    @Test
    fun `instagram names follow the desktop format`() {
        val base = postBase(post)
        assertEquals("dj_north 2023-11-03 CMus789rst", base)
        assertEquals("dj_north 2023-11-03 CMus789rst [3302000000000000009] 2.jpg", mediaFileName(base, post.items[0]))
        assertEquals("dj_north 2023-11-03 CMus789rst [CMus789rst_mix].mp4", mixName(base, post))
        assertEquals("dj_north 2023-11-03 CMus789rst song [CMus789rst_song].m4a", songName(base, post, "m4a"))
    }

    @Test
    fun `tiktok names have no date and use the id twice`() {
        val tt = MediaPost("tiktok", "7300000000000000001", "dancer", 1702000000L, items = listOf(
            MediaItem(MediaKind.IMAGE, "u", index = 5, mediaId = "7300000000000000001_5", ext = "jpg"),
        ))
        val base = postBase(tt)
        assertEquals("dancer 7300000000000000001", base)
        assertEquals("dancer 7300000000000000001 [7300000000000000001_5] 5.jpg", mediaFileName(base, tt.items[0]))
    }

    @Test
    fun `a missing owner falls back to the user in the link, then the site`() {
        assertEquals("linked 2023-11-03 CMus789rst", postBase(post.copy(owner = null), "linked"))
        assertEquals("instagram 2023-11-03 CMus789rst", postBase(post.copy(owner = null), null))
        assertEquals("dj_north CMus789rst", postBase(post.copy(takenAt = null)))
    }

    @Test
    fun `remote text cannot add path parts or brackets to a name`() {
        val base = postBase(post.copy(owner = "../a/b:[x]\n"))
        assertTrue("/" !in base && ":" !in base && "[" !in base && "\n" !in base)
    }

    @Test
    fun `song base drops the media id, the number and the song word`() {
        assertEquals("dj_north 2026-11-03 CMus789rst", songBase("dj_north 2026-11-03 CMus789rst [3302000000000000009] 2.m4a"))
        assertEquals("dancer 7300000000000000001", songBase("dancer 7300000000000000001 [7300000000000000001_5] 5.m4a"))
        assertEquals("plain", songBase("plain.m4a"))
        assertEquals("a b", songBase("a b song.m4a"))
        assertEquals("[only] 1", songBase("[only] 1.m4a"))
        assertEquals("x", songBase("x song [CODE_song].m4a"))
        assertEquals("x", songBase("x full [CODE_song].m4a"))
    }

    @Test
    fun `marker and slide number come from the file name`() {
        assertEquals("3302000000000000009", markerOf("a b [3302000000000000009] 2.jpg"))
        assertEquals("CMus789rst_mix", markerOf("a b [CMus789rst_mix].mp4"))
        assertEquals("CMus789rst_song", markerOf("a b song [CMus789rst_song].m4a"))
        assertNull(markerOf("no marker.jpg"))
        assertEquals(12, slideNumber("a [1] 12.jpg"))
        assertEquals(Int.MAX_VALUE, slideNumber("a [1].mp4"))
    }

    @Test
    fun `folder names are one safe segment`() {
        assertEquals("example_user", safeFolderName("example_user"))
        assertEquals("a_b", safeFolderName("a/b"))
        assertEquals("a_b", safeFolderName("a\\b"))
        assertNull(safeFolderName(".."))
        assertNull(safeFolderName(null))
        assertNull(safeFolderName("   "))
        assertEquals("hidden", safeFolderName(".hidden."))
        assertEquals(100, safeFolderName("x".repeat(300))!!.length)
    }

    @Test
    fun `dates are utc days`() {
        assertEquals("2023-11-26", postDate(1701000000L))
        assertNull(postDate(null))
        assertNull(postDate(0))
    }

    @Test
    fun `archive keys include the song`() {
        assertEquals("instagram" to "CMus789rst_song", MediaKeys.song(post))
        assertEquals("instagram CMus789rst_mix", MediaKeys.entry(MediaKeys.mix(post)))
    }
}
