package com.desolate.elisium.media

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** The desktop `test_mix.py` pure cases (photo seconds, canvas, probe JSON, argv) ported 1:1. */
class MediaMixTest {
    private fun inputs(argv: List<String>): List<String> =
        argv.indices.filter { argv[it] == "-i" }.map { argv[it + 1] }

    private fun slide(name: String, kind: MediaKind, seconds: Double) = Slide(File(name), kind, seconds)

    @Test
    fun `photo seconds table`() {
        assertEquals(listOf(6.0), photoSeconds(6.0, 1))
        assertEquals(listOf(3.0, 3.0, 3.0), photoSeconds(9.0, 3))
        assertEquals(listOf(2.5, 2.5), photoSeconds(5.0, 2))
        assertEquals(listOf(2.0, 2.0, 2.0), photoSeconds(3.0, 3)) // the 2 s minimum wins
        assertEquals(listOf(2.0), photoSeconds(1.0, 1))
        assertEquals(emptyList<Double>(), photoSeconds(10.0, 0))
    }

    @Test
    fun `last photo holds until the song ends`() {
        val seconds = photoSeconds(7.0, 3)
        assertEquals(7.0 / 3, seconds[0], 1e-3)
        assertEquals(seconds[0], seconds[1], 0.0)
        assertTrue(seconds.sum() >= 7.0 - 0.002)
        assertTrue(seconds.all { it >= MIN_PHOTO_SECONDS })
    }

    @Test
    fun `canvas is portrait for a tie, unknowns and squares`() {
        val tall = StreamInfo(1080, 1350)
        val wide = StreamInfo(1600, 900)
        val square = StreamInfo(1000, 1000)
        assertEquals(PORTRAIT, chooseCanvas(listOf(tall)))
        assertEquals(LANDSCAPE, chooseCanvas(listOf(wide)))
        assertEquals(LANDSCAPE, chooseCanvas(listOf(wide, wide, tall)))
        assertEquals(PORTRAIT, chooseCanvas(listOf(tall, tall, wide)))
        assertEquals(PORTRAIT, chooseCanvas(listOf(tall, wide)))
        assertEquals(LANDSCAPE, chooseCanvas(listOf(square, wide)))
        assertEquals(PORTRAIT, chooseCanvas(listOf(square)))
        assertEquals(PORTRAIT, chooseCanvas(listOf(null, null)))
        assertEquals(PORTRAIT, chooseCanvas(emptyList()))
    }

    @Test
    fun `probe json reads size, rotation and duration`() {
        val text = """{"streams":[{"codec_type":"video","width":1920,"height":1080,
            "side_data_list":[{"rotation":-90}]},{"codec_type":"audio"}],"format":{"duration":"4.5"}}"""
        val info = parseProbeJson(text)
        assertEquals(StreamInfo(1080, 1920, 4.5, hasVideo = true, hasAudio = true), info)
        assertEquals(true, info!!.portrait)
        assertNull(parseProbeJson("not json"))
        assertNull(parseProbeJson("[]"))
        assertNull(parseProbeJson(null))
        assertEquals(StreamInfo(), parseProbeJson("""{"streams": []}"""))
    }

    @Test
    fun `probe json takes the stream duration when the format has none, and the rotate tag`() {
        val info = parseProbeJson(
            """{"streams":[{"codec_type":"video","width":640,"height":360,"duration":"2.5","tags":{"rotate":"90"}}]}""",
        )
        assertEquals(StreamInfo(360, 640, 2.5, hasVideo = true, hasAudio = false), info)
    }

    @Test
    fun `cut command copies then re-encodes`() {
        val copy = buildCutCommand("ffmpeg", "in.m4a", "out.m4a", 12.5, 15.0)
        assertEquals("ffmpeg", copy[0])
        assertEquals("12.500", copy[copy.indexOf("-ss") + 1])
        assertEquals("15.000", copy[copy.indexOf("-t") + 1])
        assertTrue(copy.indexOf("-ss") < copy.indexOf("-t") && copy.indexOf("-t") < copy.indexOf("-i"))
        assertEquals("in.m4a", copy[copy.indexOf("-i") + 1])
        assertEquals("copy", copy[copy.indexOf("-c") + 1])
        assertEquals("2", copy[copy.indexOf("-threads") + 1])
        assertEquals("out.m4a", copy.last())
        val again = buildCutCommand("ffmpeg", "in.m4a", "out.m4a", 12.5, 15.0, reencode = true)
        assertFalse("copy" in again)
        assertEquals("aac", again[again.indexOf("-c:a") + 1])
        assertEquals("192k", again[again.indexOf("-b:a") + 1])
        assertTrue("-vn" in again)
    }

    @Test
    fun `mix command for one photo`() {
        val argv = buildMixCommand("ffmpeg", listOf(slide("a.jpg", MediaKind.IMAGE, 6.0)), "song.m4a", "out.mp4", PORTRAIT)
        assertEquals(listOf("a.jpg", "song.m4a"), inputs(argv))
        val graph = argv[argv.indexOf("-filter_complex") + 1]
        assertTrue("scale=1080:1920:force_original_aspect_ratio=decrease:out_range=tv" in graph)
        assertTrue("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" in graph)
        assertTrue("concat=n=1:v=1:a=0[v]" in graph)
        assertTrue("[1:a]" in graph && "apad=whole_dur=6.000" in graph)
        assertEquals(1, argv.count { it == "-loop" })
        assertEquals("6.000", argv[argv.indexOf("-t") + 1])
        assertEquals("libx264", argv[argv.indexOf("-c:v") + 1])
        assertEquals("yuv420p", argv[argv.indexOf("-pix_fmt") + 1])
        assertEquals("30", argv[argv.indexOf("-r") + 1])
        assertEquals("aac", argv[argv.indexOf("-c:a") + 1])
        assertEquals("2", argv[argv.indexOf("-threads") + 1])
        assertEquals("out.mp4", argv.last())
        assertFalse("-shortest" in argv)
    }

    @Test
    fun `mix command for three photos shows each for its share`() {
        val slides = "abc".map { slide("$it.jpg", MediaKind.IMAGE, 3.0) }
        val argv = buildMixCommand("ffmpeg", slides, "s.m4a", "o.mp4", LANDSCAPE)
        assertEquals(listOf("a.jpg", "b.jpg", "c.jpg", "s.m4a"), inputs(argv))
        assertEquals(3, argv.count { it == "-loop" })
        val graph = argv[argv.indexOf("-filter_complex") + 1]
        assertTrue("concat=n=3:v=1:a=0[v]" in graph && "[v0][v1][v2]concat" in graph)
        assertTrue("scale=1920:1080" in graph && "[3:a]" in graph)
        val durations = argv.indices.filter { argv[it] == "-t" }.map { argv[it + 1] }
        assertEquals(listOf("3.000", "3.000", "3.000", "9.000"), durations) // each photo, then the whole video
    }

    @Test
    fun `mixed carousel keeps slide order and drops the clip's own sound`() {
        val slides = listOf(
            slide("1.jpg", MediaKind.IMAGE, 2.0),
            slide("2.mp4", MediaKind.VIDEO, 4.5),
            slide("3.jpg", MediaKind.IMAGE, 2.0),
        )
        val argv = buildMixCommand("ffmpeg", slides, "s.m4a", "o.mp4")
        assertEquals(listOf("1.jpg", "2.mp4", "3.jpg", "s.m4a"), inputs(argv))
        assertEquals(2, argv.count { it == "-loop" }) // the clip is not looped
        val graph = argv[argv.indexOf("-filter_complex") + 1]
        assertTrue("[1:v]scale" in graph && "[1:a]" !in graph && "[2:a]" !in graph)
        assertTrue("[3:a]" in graph && "apad=whole_dur=8.500" in graph)
        val outputT = argv.indices.first { it > argv.indexOf("-c:a") && argv[it] == "-t" }
        assertEquals("8.500", argv[outputT + 1])
        val maps = argv.indices.filter { argv[it] == "-map" }.map { argv[it + 1] }
        assertEquals(listOf("[v]", "[a]"), maps)
    }

    @Test
    fun `mix command needs slides`() {
        try {
            buildMixCommand("ffmpeg", emptyList(), "s.m4a", "o.mp4")
            fail("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }

    @Test
    fun `seconds always use a dot, whatever the locale`() {
        val saved = java.util.Locale.getDefault()
        try {
            java.util.Locale.setDefault(java.util.Locale.GERMANY)
            assertEquals("12.500", clock(12.5))
            assertTrue("12.500" in buildCutCommand("f", "i", "o", 12.5, 3.0))
        } finally {
            java.util.Locale.setDefault(saved)
        }
    }

    @Test
    fun `clip times need a start and a positive length`() {
        assertEquals(15.4 to 15.0, clipTimes(MusicClip("u", startMs = 15400, durationMs = 15000)))
        assertNull(clipTimes(MusicClip("u", startMs = 15400)))
        assertNull(clipTimes(MusicClip("u", durationMs = 15000)))
        assertNull(clipTimes(MusicClip("u", startMs = 1000, durationMs = 0)))
        assertNull(clipTimes(MusicClip("u", startMs = -1, durationMs = 5000)))
        assertNull(clipTimes(null))
        assertNotNull(clipTimes(MusicClip("u", startMs = 0, durationMs = 1)))
    }
}
