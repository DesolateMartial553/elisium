package com.desolate.elisium.media

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** ffmpeg stand-in: records argv, writes the output file named by the last argument. */
class FakeFfmpeg(
    var hasProbe: Boolean = true,
    var failCut: Int = 0, // how many cut attempts fail
    var failMix: Boolean = false,
    var cancelAfterCut: Boolean = false,
) : FfmpegSession {
    val runs = ArrayList<List<String>>()
    val probes = HashMap<String, String>()
    var songSeconds = "15.0"
    override val ffmpegPath = "ffmpeg"
    override val ffprobePath: String? get() = if (hasProbe) "ffprobe" else null
    override var cancelled = false

    override fun run(argv: List<String>, timeoutMs: Long): Boolean {
        runs.add(argv)
        val isMix = "-filter_complex" in argv
        if (isMix) {
            if (failMix) return false
            File(argv.last()).writeText("mp4")
            return true
        }
        if (failCut > 0) {
            failCut--
            return false
        }
        File(argv.last()).writeText("snippet")
        if (cancelAfterCut) cancelled = true
        return !cancelled
    }

    override fun probeJson(file: File): String? {
        if (!hasProbe) return null
        probes[file.name]?.let { return it }
        return """{"streams":[{"codec_type":"audio"}],"format":{"duration":"$songSeconds"}}"""
    }

    override fun terminate() {
        cancelled = true
    }
}

class MediaConverterTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val items = (1..3).map {
        MediaItem(MediaKind.IMAGE, "https://x/$it.jpg", 1080, 1350, it, "33000000000000000$it", "jpg")
    }
    private val post = MediaPost(
        "instagram", "CMus789rst", "dj_north", 1699000000L, "cap", items,
        MusicClip("https://x/song.m4a", "T", "A", startMs = 15400, durationMs = 15000),
    )
    private val base = postBase(post)

    private fun stage(withSong: Boolean = true): Triple<File, List<Visual>, File?> {
        val dir = tmp.newFolder()
        val visuals = items.map { item ->
            val f = File(dir, mediaFileName(base, item)).apply { writeText("img") }
            Visual(f, item.kind, item.width, item.height)
        }
        val song = if (withSong) File(dir, fullSongName(base, post, "m4a")).apply { writeText("full") } else null
        return Triple(dir, visuals, song)
    }

    private fun convert(
        dir: File, visuals: List<Visual>, song: File?, session: FfmpegSession?,
        existingMix: Boolean = false, makeVideo: Boolean = true, cutSong: Boolean = true,
        post: MediaPost = this.post, onConvert: () -> Unit = {},
    ) = convertStaging(dir, post, base, song, visuals, session, existingMix, onConvert, makeVideo, cutSong)

    private fun names(dir: File) = dir.listFiles()!!.map { it.name }.sorted()

    @Test
    fun `cuts the snippet and builds the video from three photos`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg()
        var converting = 0
        val result = convert(dir, visuals, song, ff, onConvert = { converting++ })
        assertEquals("$base song [CMus789rst_song].m4a", result.song!!.name)
        assertEquals("$base [CMus789rst_mix].mp4", result.video!!.name)
        assertNull(result.note)
        assertTrue(result.attemptedVideo)
        assertEquals(1, converting) // once, before the first ffmpeg run
        val cut = ff.runs[0]
        assertEquals("15.400", cut[cut.indexOf("-ss") + 1])
        assertEquals("15.000", cut[cut.indexOf("-t") + 1])
        assertTrue("copy" in cut)
        val mix = ff.runs[1]
        assertTrue("scale=1080:1920" in mix[mix.indexOf("-filter_complex") + 1])
        // the song is probed for its length: 15 s / 3 photos
        assertEquals(3, mix.count { it == "-loop" })
        assertEquals("5.000", mix[mix.indexOf("-t") + 1])
        // the whole track and the scratch work are gone
        assertFalse(names(dir).any { " full [" in it || it.startsWith(".") })
        assertEquals(5, names(dir).size) // 3 photos + song + video
    }

    @Test
    fun `a failed stream copy retries with aac and keeps the m4a name`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg(failCut = 1)
        val result = convert(dir, visuals, song, ff, makeVideo = false)
        assertEquals(2, ff.runs.size)
        assertFalse("copy" in ff.runs[1])
        assertEquals("aac", ff.runs[1][ff.runs[1].indexOf("-c:a") + 1])
        assertEquals("$base song [CMus789rst_song].m4a", result.song!!.name)
        assertNull(result.note)
    }

    @Test
    fun `a failed trim keeps the full song under the song name, with a note`() {
        val (dir, visuals, song) = stage()
        val result = convert(dir, visuals, song, FakeFfmpeg(failCut = 2), makeVideo = false)
        assertEquals(TRIM_FAILED_NOTE, result.note)
        assertEquals("$base song [CMus789rst_song].m4a", result.song!!.name)
        assertEquals("full", result.song!!.readText())
    }

    @Test
    fun `no snippet times keeps the full song with a note and still builds the video`() {
        val (dir, visuals, song) = stage()
        val noTimes = post.copy(music = post.music!!.copy(startMs = null, durationMs = null))
        val ff = FakeFfmpeg().apply { songSeconds = "9.0" }
        val result = convert(dir, visuals, song, ff, post = noTimes)
        assertEquals(FULL_SONG_NOTE, result.note)
        assertEquals(1, ff.runs.size) // no cut, only the mix
        assertNotNull(result.video)
        assertEquals("full", result.song!!.readText())
    }

    @Test
    fun `no song means nothing happens`() {
        val (dir, visuals, _) = stage(withSong = false)
        val ff = FakeFfmpeg()
        val result = convert(dir, visuals, null, ff)
        assertNull(result.song)
        assertNull(result.video)
        assertNull(result.note)
        assertTrue(ff.runs.isEmpty())
    }

    @Test
    fun `missing ffmpeg still keeps photos and song with the same notes as desktop`() {
        val (dir, visuals, song) = stage()
        val result = convert(dir, visuals, song, null)
        assertEquals("$TRIM_FAILED_NOTE $MIX_FAILED_NOTE", result.note)
        assertNull(result.video)
        assertEquals("$base song [CMus789rst_song].m4a", result.song!!.name)

        val (d2, v2, s2) = stage()
        val noTimes = post.copy(music = post.music!!.copy(startMs = null))
        assertEquals("$FULL_SONG_NOTE $MIX_FAILED_NOTE", convert(d2, v2, s2, null, post = noTimes).note)

        val (d3, v3, s3) = stage()
        assertEquals(MIX_FAILED_NOTE, convert(d3, v3, s3, null, cutSong = false).note)

        val (d4, v4, s4) = stage()
        assertNull(convert(d4, v4, s4, null, makeVideo = false, cutSong = false).note)
    }

    @Test
    fun `a failed mix is a note, not an error`() {
        val (dir, visuals, song) = stage()
        val result = convert(dir, visuals, song, FakeFfmpeg(failMix = true))
        assertEquals(MIX_FAILED_NOTE, result.note)
        assertNull(result.video)
        assertNotNull(result.song)
        assertFalse(names(dir).any { it.endsWith(".mp4") || it.startsWith(".") })
    }

    @Test
    fun `a video already in the output folder is not built again`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg()
        val result = convert(dir, visuals, song, ff, existingMix = true)
        assertNull(result.video)
        assertFalse(result.attemptedVideo)
        assertNull(result.note)
        assertEquals(1, ff.runs.size) // only the cut
    }

    @Test
    fun `a video already in staging is kept`() {
        val (dir, visuals, song) = stage()
        File(dir, mixName(base, post)).writeText("old")
        val ff = FakeFfmpeg()
        val result = convert(dir, visuals, song, ff)
        assertFalse(result.attemptedVideo)
        assertEquals("old", File(dir, mixName(base, post)).readText())
    }

    @Test
    fun `photos and song only builds no video`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg()
        val result = convert(dir, visuals, song, ff, makeVideo = false)
        assertNull(result.video)
        assertFalse(result.attemptedVideo)
        assertEquals(1, ff.runs.size)
        assertNull(result.note)
    }

    @Test
    fun `full song skips the cut without a note`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg().apply { songSeconds = "30.0" }
        val result = convert(dir, visuals, song, ff, cutSong = false)
        assertNull(result.note)
        assertEquals(1, ff.runs.size) // the mix only
        val mix = ff.runs[0]
        assertEquals("10.000", mix[mix.indexOf("-t") + 1]) // 30 s over 3 photos
        assertEquals("full", result.song!!.readText())
        assertEquals("$base song [CMus789rst_song].m4a", result.song!!.name)
    }

    @Test
    fun `an already cut song is not cut again`() {
        val (dir, visuals, _) = stage(withSong = false)
        File(dir, songName(base, post, "m4a")).writeText("snippet")
        val ff = FakeFfmpeg()
        val result = convert(dir, visuals, null, ff)
        assertEquals(1, ff.runs.size)
        assertTrue("-filter_complex" in ff.runs[0])
        assertEquals("snippet", result.song!!.readText())
        assertNotNull(result.video)
    }

    @Test
    fun `a mixed carousel orders slides by number, probes clips and picks the canvas`() {
        val dir = tmp.newFolder()
        val mixed = listOf(
            MediaItem(MediaKind.IMAGE, "u", 1600, 900, 1, "a1", "jpg"),
            MediaItem(MediaKind.VIDEO, "u", null, null, 2, "a2", "mp4"),
            MediaItem(MediaKind.IMAGE, "u", 1600, 900, 3, "a3", "jpg"),
        )
        val p = post.copy(items = mixed)
        val files = mixed.map { File(dir, mediaFileName(base, it)).apply { writeText("x") } }
        val song = File(dir, fullSongName(base, p, "m4a")).apply { writeText("full") }
        // given out of order on purpose
        val visuals = listOf(2, 0, 1).map { Visual(files[it], mixed[it].kind, mixed[it].width, mixed[it].height) }
        val ff = FakeFfmpeg()
        ff.probes[files[1].name] = """{"streams":[{"codec_type":"video","width":1080,"height":1920}],"format":{"duration":"4.5"}}"""
        val result = convertStaging(dir, p, base, song, visuals, ff, false, {}, makeVideo = true, cutSong = true)
        assertNotNull(result.video)
        val mix = ff.runs.single { "-filter_complex" in it }
        val inputs = mix.indices.filter { mix[it] == "-i" }.map { File(mix[it + 1]).name }
        assertEquals(files.map { it.name } + result.song!!.name, inputs)
        assertEquals(2, mix.count { it == "-loop" })
        val graph = mix[mix.indexOf("-filter_complex") + 1]
        assertTrue("scale=1920:1080" in graph) // two wide pictures against no tall ones
        assertTrue("[1:a]" !in graph && "[3:a]" in graph)
    }

    @Test
    fun `an unknown clip length makes the mix fail gracefully`() {
        val dir = tmp.newFolder()
        val mixed = listOf(
            MediaItem(MediaKind.IMAGE, "u", 1080, 1350, 1, "b1", "jpg"),
            MediaItem(MediaKind.VIDEO, "u", null, null, 2, "b2", "mp4"),
        )
        val p = post.copy(items = mixed)
        val files = mixed.map { File(dir, mediaFileName(base, it)).apply { writeText("x") } }
        val song = File(dir, fullSongName(base, p, "m4a")).apply { writeText("full") }
        val visuals = files.indices.map { Visual(files[it], mixed[it].kind, mixed[it].width, mixed[it].height) }
        val ff = FakeFfmpeg().apply { probes[files[1].name] = "not json" }
        val result = convertStaging(dir, p, base, song, visuals, ff, false, {}, makeVideo = true, cutSong = true)
        assertNull(result.video)
        assertEquals(MIX_FAILED_NOTE, result.note)
    }

    @Test
    fun `without ffprobe the snippet length times the mix`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg(hasProbe = false)
        val result = convert(dir, visuals, song, ff)
        assertNotNull(result.video)
        val mix = ff.runs.last()
        assertEquals("5.000", mix[mix.indexOf("-t") + 1]) // the post's 15 s over 3 photos
    }

    @Test
    fun `terminating ffmpeg while cutting reports cancelled and leaves no scratch`() {
        val (dir, visuals, song) = stage()
        val ff = FakeFfmpeg(cancelAfterCut = true)
        val result = convert(dir, visuals, song, ff)
        assertTrue(result.cancelled)
        assertNull(result.video)
        assertFalse(names(dir).any { it.startsWith(".") })
    }
}
