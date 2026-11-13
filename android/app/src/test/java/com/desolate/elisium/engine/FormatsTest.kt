package com.desolate.elisium.engine

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

private fun obj(text: String): JsonObject = Json.parseToJsonElement(text) as JsonObject

class FormatsTest {
    private val info = obj(
        """
        {"formats": [
          {"format_id": "sb0", "ext": "mhtml", "format_note": "storyboard", "vcodec": "none", "acodec": "none", "height": 90, "width": 160},
          {"format_id": "139", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.5", "abr": 48.5, "tbr": 49, "filesize": 1000000},
          {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129.5, "tbr": 130, "filesize_approx": 3500000, "format_note": "medium"},
          {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none", "width": 1920, "height": 1080, "fps": 30, "tbr": 4000, "filesize": 80000000},
          {"format_id": "136", "ext": "mp4", "vcodec": "avc1.4d401f", "acodec": "none", "width": 1280, "height": 720, "fps": 60, "vbr": 2000},
          {"format_id": "18", "ext": "mp4", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "width": 640, "height": 360, "fps": 30, "tbr": 500},
          {"format_id": "nothing", "ext": "x", "vcodec": "none", "acodec": "none"},
          {"ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 10}
        ]}
        """,
    )

    private fun expectIllegal(block: () -> Unit) {
        try {
            block()
            fail("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }

    @Test
    fun `format rows kinds sorting and skips`() {
        val rows = formatRows(info)
        assertEquals(listOf("18", "137", "136", "140", "139"), rows.map { it.formatId })
        val byId = rows.associateBy { it.formatId }
        assertEquals("video+audio", byId.getValue("18").kind)
        assertEquals("video", byId.getValue("137").kind)
        assertEquals("1920x1080", byId.getValue("137").resolution)
        assertEquals("audio", byId.getValue("140").kind)
        assertEquals("audio only", byId.getValue("140").resolution)
        assertEquals("medium", byId.getValue("140").note)
        assertFalse(rows.any { it.formatId == "sb0" || it.ext == "mhtml" })
    }

    @Test
    fun `format rows sizes and bitrate fallbacks`() {
        val byId = formatRows(info).associateBy { it.formatId }
        assertEquals(80_000_000L, byId.getValue("137").sizeBytes)
        assertEquals(3_500_000L, byId.getValue("140").sizeBytes) // filesize_approx
        assertNull(byId.getValue("136").sizeBytes)
        assertEquals(2000.0, byId.getValue("136").bitrate!!, 0.0) // from vbr
        assertEquals(30.0, byId.getValue("18").fps!!, 0.0)
    }

    @Test
    fun `format rows tolerates garbage`() {
        assertEquals(emptyList<FormatRow>(), formatRows(obj("{}")))
        assertEquals(emptyList<FormatRow>(), formatRows(obj("""{"formats": null}""")))
        assertEquals(emptyList<FormatRow>(), formatRows(obj("""{"formats": ["x", null, 3]}""")))
    }

    @Test
    fun `format rows without codec keys`() {
        val rows = formatRows(
            obj("""{"formats": [{"format_id": "a", "ext": "mp3"}, {"format_id": "b", "ext": "mp4", "height": 480}]}"""),
        )
        assertEquals(mapOf("a" to "audio", "b" to "video+audio"), rows.associate { it.formatId to it.kind })
    }

    @Test
    fun `selector for`() {
        val cases = listOf(
            Triple("137", "140", "137+140"), Triple("137", null, "137"), Triple(null, "140", "140"),
            Triple(" 18 ", "", "18"), Triple("", " 140", "140"),
        )
        for ((video, audio, expected) in cases) assertEquals(expected, selectorFor(video, audio))
    }

    @Test
    fun `selector for errors`() {
        val cases = listOf(
            null to null, "" to "", "  " to null, "1+2" to null, null to "a b",
        )
        for ((video, audio) in cases) expectIllegal { selectorFor(video, audio) }
    }

    @Test
    fun `human helpers`() {
        assertEquals("unknown", humanSize(null))
        assertEquals("512 B", humanSize(512))
        assertEquals("1.5 KB", humanSize(1536))
        assertEquals("5.0 MB", humanSize(5 * 1024 * 1024))
        assertEquals("", humanDuration(null))
        assertEquals("1:05", humanDuration(65))
        assertEquals("1:02:05", humanDuration(3725))
    }

    @Test
    fun `human helpers round like python`() {
        assertEquals("1.2 KB", humanSize(1280)) // 1.25 -> half-even, like Python's format
        assertEquals("unknown", humanSize(-1))
        assertEquals("0:02", humanDuration(2.5)) // round() is half-to-even
        assertEquals("0:04", humanDuration(3.5))
        assertEquals("", humanDuration(-1))
    }

    @Test
    fun summary() {
        val s = summary(
            obj(
                """{"title": " T ", "uploader": "U", "duration": 61.4, "thumbnail": "https://i/x.jpg", "webpage_url": "https://w"}""",
            ),
        )
        assertEquals("T", s.title)
        assertEquals("U", s.uploader)
        assertEquals(61, s.duration)
        assertEquals("https://i/x.jpg", s.thumbnail)
        assertEquals("https://w", s.webpageUrl)
        val empty = summary(obj("{}"))
        assertEquals("Untitled video", empty.title)
        assertNull(empty.duration)
        assertNull(empty.thumbnail)
        val thumbs = summary(obj("""{"channel": "C", "thumbnails": [{"url": "a"}, {"url": "b"}]}"""))
        assertEquals("C", thumbs.uploader)
        assertEquals("b", thumbs.thumbnail)
    }

    @Test
    fun `playlist entries none and flat`() {
        val entries = playlistEntries(
            obj(
                """
                {"entries": [
                  {"id": "aaa", "title": "One", "url": "https://www.youtube.com/watch?v=aaa", "duration": 90},
                  null,
                  {"id": "ccc", "ie_key": "Youtube", "url": "ccc"},
                  {"id": "ddd", "title": "[Private video]", "url": "https://www.youtube.com/watch?v=ddd"},
                  {"title": "No url"},
                  {"url": "https://vimeo.com/9", "ie_key": "Vimeo"}
                ]}
                """,
            ),
        )
        assertEquals(listOf(1, 2, 3, 4, 5, 6), entries.map { it.index })
        assertTrue(entries[0].available)
        assertEquals(90, entries[0].duration)
        assertEquals("One", entries[0].title)
        assertFalse(entries[1].available)
        assertNull(entries[1].url)
        assertEquals("https://www.youtube.com/watch?v=ccc", entries[2].url)
        assertTrue(entries[2].available)
        assertFalse(entries[3].available)
        assertFalse(entries[4].available)
        assertEquals("https://vimeo.com/9", entries[5].url)
        assertEquals("https://vimeo.com/9", entries[5].title)
        assertEquals(emptyList<PlaylistEntry>(), playlistEntries(obj("{}")))
    }

    @Test
    fun `parse range`() {
        assertEquals(emptyList<Int>(), parseRange("", 10))
        assertEquals(listOf(3, 4, 5), parseRange("3-5", 10))
        assertEquals(listOf(1, 4, 9, 10, 11, 12), parseRange("1,4,9-12", 12))
        assertEquals(listOf(1, 2), parseRange(" 2 , 2 ,1 ", 5))
        assertEquals(listOf(7), parseRange("7", 7))
    }

    @Test
    fun `parse range errors are plain`() {
        for (text in listOf("abc", "3-", "-3", "0", "1,,2", "5-3", "1-99", "1.5", "2-x")) {
            try {
                parseRange(text, 10)
                fail("accepted '$text'")
            } catch (e: IllegalArgumentException) {
                assertNotNull(e.message)
                assertTrue(e.message!!.isNotEmpty() && "Traceback" !in e.message!!)
            }
        }
    }

    @Test
    fun `parse range messages match python`() {
        fun msg(text: String, total: Int = 10) =
            try { parseRange(text, total); "" } catch (e: IllegalArgumentException) { e.message }
        assertEquals("Numbers start at 1.", msg("0"))
        assertEquals("\"5-3\" runs backwards; write it as 3-5.", msg("5-3"))
        assertEquals("99 is past the end; this playlist has 10 videos.", msg("1-99"))
        assertEquals("2 is past the end; this playlist has 1 video.", msg("2", 1))
        assertEquals("There is an extra comma. Use numbers like 3-15 or 1,4,9-12.", msg("1,,2"))
        assertEquals("\"-3\" is not a number or a range. Use numbers like 3-15 or 1,4,9-12.", msg("-3"))
    }

    @Test
    fun `format row is a value type`() {
        val row = formatRows(info)[0]
        assertEquals(row, row.copy())
    }
}
