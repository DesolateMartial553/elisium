package com.desolate.elisium.backend

import com.desolate.elisium.engine.DownloadRequest
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private fun request(
    limitRate: String? = null,
    extra: List<String> = emptyList(),
    selector: String = "bestvideo*+bestaudio/best",
) = DownloadRequest(
    url = "https://youtu.be/dQw4w9WgXcQ",
    formatSelector = selector,
    extraArgs = extra,
    limitRate = limitRate,
    archiveFile = File("/data/archive.txt"),
    stagingDir = File("/data/staging"),
    processId = "item-7",
)

class YtDlpCommandsTest {
    @Test
    fun argvMatchesTheDesktopOrderAndAddsNoMtime() {
        val argv = buildDownloadArgv(request())
        assertEquals(
            listOf(
                "-P", "home:/data/staging",
                "-P", "temp:/data/staging/tmp",
                "--download-archive", "/data/archive.txt",
                "--no-overwrites",
                "--no-mtime",
                "-o", "%(title).150B [%(id)s].%(ext)s",
                "--continue",
                "--newline",
                "--progress-template", "download:%(progress)j",
                "--progress-template", "postprocess:%(progress)j",
                "--retries", "3",
                "--fragment-retries", "3",
                "-f", "bestvideo*+bestaudio/best",
                "--print-to-file", "after_move:filepath", "/data/staging/item-7.path",
                "https://youtu.be/dQw4w9WgXcQ",
            ),
            argv,
        )
    }

    @Test
    fun outputTemplateKeepsTheIdAndLimitsTheTitle() {
        assertEquals("%(title).150B [%(id)s].%(ext)s", OUTPUT_TEMPLATE)
    }

    @Test
    fun homeComesBeforeTemp() {
        val argv = buildDownloadArgs(request())
        assertTrue(argv.indexOf("home:/data/staging") < argv.indexOf("temp:/data/staging/tmp"))
    }

    @Test
    fun bothProgressTemplatesArePresent() {
        val argv = buildDownloadArgs(request())
        val templates = argv.indices.filter { argv[it] == "--progress-template" }.map { argv[it + 1] }
        assertEquals(listOf("download:%(progress)j", "postprocess:%(progress)j"), templates)
    }

    @Test
    fun limitRateOnlyWhenSet() {
        assertFalse("--limit-rate" in buildDownloadArgs(request()))
        assertFalse("--limit-rate" in buildDownloadArgs(request(limitRate = "")))
        val args = buildDownloadArgs(request(limitRate = "2M"))
        assertEquals("2M", args[args.indexOf("--limit-rate") + 1])
    }

    @Test
    fun extraArgsComeBeforeTheUrlAndKeepOrder() {
        val argv = buildDownloadArgv(request(extra = listOf("-x", "--audio-format", "mp3")))
        assertEquals("https://youtu.be/dQw4w9WgXcQ", argv.last())
        assertEquals(listOf("-x", "--audio-format", "mp3"), argv.subList(argv.size - 4, argv.size - 1))
    }

    @Test
    fun selectorIsPassedVerbatim() {
        val args = buildDownloadArgs(request(selector = "wv*+wa/w"))
        assertEquals("wv*+wa/w", args[args.indexOf("-f") + 1])
    }

    @Test
    fun pathFileAndTempDirAreInsideStaging() {
        assertEquals(File("/data/staging/tmp"), tempDirFor(File("/data/staging")))
        assertEquals(File("/data/staging/item-3.path"), pathFileFor(File("/data/staging"), "item-3"))
    }

    @Test
    fun probeArgsUseNoPlaylistForAVideoAndFlatPlaylistForAList() {
        assertEquals(listOf("-J", "--no-download", "--no-playlist"), buildProbeArgs("https://youtu.be/dQw4w9WgXcQ"))
        assertEquals(
            listOf("-J", "--no-download", "--flat-playlist"),
            buildProbeArgs("https://www.youtube.com/playlist?list=PL1"),
        )
    }

    @Test
    fun playlistDetection() {
        assertTrue(looksLikePlaylist("https://www.youtube.com/playlist?list=PL123"))
        assertTrue(looksLikePlaylist("https://www.youtube.com/watch?list=PL123"))
        assertTrue(looksLikePlaylist("https://example.com/playlist/abc"))
        assertTrue(looksLikePlaylist("https://example.com/playlist"))
        assertTrue(looksLikePlaylist("  https://www.youtube.com/playlist?list=PL1#frag "))
        assertFalse(looksLikePlaylist("https://www.youtube.com/watch?v=abc&list=PL123"))
        assertFalse(looksLikePlaylist("https://www.youtube.com/watch?v=abc"))
        assertFalse(looksLikePlaylist("https://youtu.be/abc?list=PL1&v=abc"))
        assertFalse(looksLikePlaylist("https://example.com/watch/playlist"))
        assertFalse(looksLikePlaylist("https://www.youtube.com/watch?list="))
        assertFalse(looksLikePlaylist("https://example.com/"))
        assertFalse(looksLikePlaylist(""))
    }

    @Test
    fun playlistDetectionDecodesTheQuery() {
        assertTrue(looksLikePlaylist("https://x.com/watch?%6Cist=PL1"))
        assertFalse(looksLikePlaylist("https://x.com/watch?v=%41&list=PL1"))
    }

    @Test
    fun pathFileTakesTheLastNonBlankLine() {
        assertEquals("/b.mp4", parsePathFile("/a.mp4\n\n/b.mp4\n  \n"))
        assertNull(parsePathFile("  \n\n"))
        assertNull(parsePathFile(null))
    }

    @Test
    fun outcomeReadsThePathFile() {
        val o = interpretOutcome(0, "log", "/data/staging/V [id].mp4\n", terminated = false)
        assertEquals("/data/staging/V [id].mp4", o.filePath)
        assertFalse(o.alreadyArchived)
        assertFalse(o.terminated)
        assertEquals(0, o.exitCode)
        assertEquals("log", o.rawLog)
    }

    @Test
    fun outcomeDetectsAnAlreadyArchivedVideo() {
        val log = "[youtube] abc: Downloading\n[download] abc has already been recorded in the archive"
        val o = interpretOutcome(0, log, null, terminated = false)
        assertNull(o.filePath)
        assertTrue(o.alreadyArchived)
    }

    @Test
    fun archivedMarkerWithAPathIsNotAlreadyArchived() {
        val o = interpretOutcome(0, "has already been recorded in the archive", "/x.mp4", terminated = false)
        assertEquals("/x.mp4", o.filePath)
        assertFalse(o.alreadyArchived)
    }

    @Test
    fun terminatedAndFailedRunsReportNoFile() {
        val killed = interpretOutcome(143, "", "/old.mp4", terminated = true)
        assertTrue(killed.terminated)
        assertNull(killed.filePath)
        assertFalse(killed.alreadyArchived)
        val failed = interpretOutcome(1, "ERROR: boom", "/old.mp4", terminated = false)
        assertNull(failed.filePath)
        assertEquals(1, failed.exitCode)
        assertFalse(failed.terminated)
    }

    @Test
    fun failedRunNeverCountsAsArchived() {
        assertFalse(interpretOutcome(1, "has already been recorded in the archive", null, false).alreadyArchived)
    }
}
