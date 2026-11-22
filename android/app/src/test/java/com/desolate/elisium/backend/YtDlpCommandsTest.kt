package com.desolate.elisium.backend

import com.desolate.elisium.engine.DownloadRequest
import com.desolate.elisium.engine.expectedBytesFrom
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
    cookies: File? = null,
) = DownloadRequest(
    url = "https://youtu.be/dQw4w9WgXcQ",
    formatSelector = selector,
    extraArgs = extra,
    limitRate = limitRate,
    archiveFile = File("/data/archive.txt"),
    stagingDir = File("/data/staging"),
    processId = "item-7",
    cookiesFile = cookies,
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
                "--no-playlist",
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
    fun withoutTheSavedLookupTheArgvIsExactlyToday() {
        // "Faster downloads: Off" (or an unusable lookup) leaves infoJson null: same argv as before, link last.
        val plain = request()
        assertEquals(buildDownloadArgs(plain) + "https://youtu.be/dQw4w9WgXcQ", buildDownloadArgv(plain))
        assertFalse("--load-info-json" in buildDownloadArgv(plain))
        assertEquals("https://youtu.be/dQw4w9WgXcQ", runnerUrlFor(plain))
    }

    @Test
    fun theSavedLookupIsLoadedInsteadOfTheLink() {
        val withInfo = request().copy(infoJson = File("/data/staging/tmp/item-7.info.json"))
        val argv = buildDownloadArgv(withInfo)
        assertEquals("--load-info-json", argv[argv.size - 2])
        assertEquals("/data/staging/tmp/item-7.info.json", argv.last())
        assertFalse("the link must not be passed", "https://youtu.be/dQw4w9WgXcQ" in argv)
        assertEquals("", runnerUrlFor(withInfo))
        // Everything else is unchanged and in the same order.
        assertEquals(buildDownloadArgs(request()), argv.dropLast(2))
    }

    @Test
    fun everyDownloadPassesNoPlaylist() {
        // Items reach the queue as single video URLs (Android has no playlist picker), so a watch?v=..&list=.. link
        // must not pull in the whole playlist. For a real playlist URL the flag changes nothing.
        assertTrue("--no-playlist" in buildDownloadArgs(request()))
        assertTrue("--no-playlist" in buildDownloadArgs(request(extra = listOf("-x"))))
    }

    @Test
    fun classifiableTextDropsTitlesFromStdout() {
        val stdout = "[download] Destination: Connection Lost - Private Video Tour [abc].mp4\nERROR: Requested format is not available"
        val text = classifiableText(stdout, "")
        assertFalse("Connection Lost" in text)
        assertTrue("Requested format is not available" in text)
    }

    @Test
    fun classifiableTextKeepsStderrAndWarnings() {
        val text = classifiableText("[info] My Title\nWARNING: slow\n", "ERROR: HTTP Error 403: Forbidden")
        assertTrue("HTTP Error 403" in text)
        assertTrue("WARNING: slow" in text)
        assertFalse("My Title" in text)
    }

    @Test
    fun expectedBytesPrefersFilesizeThenApprox() {
        fun info(s: String) = kotlinx.serialization.json.Json.parseToJsonElement(s) as kotlinx.serialization.json.JsonObject
        assertEquals(1000L, expectedBytesFrom(info("""{"filesize": 1000, "filesize_approx": 5}""")))
        assertEquals(5L, expectedBytesFrom(info("""{"filesize": null, "filesize_approx": 5.0}""")))
        assertNull(expectedBytesFrom(info("""{"filesize": 0}""")))
        assertNull(expectedBytesFrom(info("{}")))
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

    // -- cookies and stories (brief 8B) --------------------------------------------------
    @Test
    fun cookiesOnlyWhenTheFileIsGiven() {
        assertFalse("--cookies" in buildDownloadArgs(request()))
        val jar = File("/data/cookies/cookies.txt")
        val args = buildDownloadArgs(request(cookies = jar))
        assertEquals("/data/cookies/cookies.txt", args[args.indexOf("--cookies") + 1])
        // After --limit-rate, before the preset's extra args, so yt-dlp sees one coherent option list.
        val withBoth = buildDownloadArgs(request(limitRate = "2M", extra = listOf("-x"), cookies = jar))
        assertTrue(withBoth.indexOf("--limit-rate") < withBoth.indexOf("--cookies"))
        assertTrue(withBoth.indexOf("--cookies") < withBoth.indexOf("-x"))
    }

    @Test
    fun probeCarriesTheCookiesFileWithoutReadingIt() {
        assertEquals(
            listOf("-J", "--no-download", "--no-playlist", "--cookies", "/data/cookies/cookies.txt"),
            buildProbeArgs("https://youtu.be/abc", File("/data/cookies/cookies.txt")),
        )
        assertEquals(listOf("-J", "--no-download", "--no-playlist"), buildProbeArgs("https://youtu.be/abc"))
    }

    @Test
    fun instagramStoryTraysArePlaylists() {
        assertTrue(looksLikePlaylist("https://www.instagram.com/stories/someone/"))
        assertTrue(looksLikePlaylist("https://instagram.com/stories/someone"))
        assertTrue(looksLikePlaylist("https://www.instagram.com/stories/highlights/1791234567890/"))
        assertTrue(looksLikePlaylist("https://m.instagram.com/stories/someone/?utm_source=x"))
    }

    @Test
    fun oneStoryWithItsOwnIdIsASingleItem() {
        assertFalse(looksLikePlaylist("https://www.instagram.com/stories/someone/3412345678901234567/"))
        // A highlight tray without its id is not a list either.
        assertFalse(looksLikePlaylist("https://www.instagram.com/stories/highlights/"))
        assertFalse(looksLikePlaylist("https://www.instagram.com/stories/someone/highlights/"))
    }

    @Test
    fun instagramAndTiktokVideosAreSingleItems() {
        assertFalse(looksLikePlaylist("https://www.instagram.com/reel/CabcDEF123/"))
        assertFalse(looksLikePlaylist("https://www.instagram.com/p/CabcDEF123/"))
        assertFalse(looksLikePlaylist("https://www.tiktok.com/@tiktok/video/7106594312292453675"))
        assertFalse(looksLikePlaylist("https://vm.tiktok.com/ZMabc123/"))
        // Another site's /stories/ path is not an Instagram tray.
        assertFalse(looksLikePlaylist("https://example.com/stories/someone/"))
    }

    @Test
    fun storyTraysProbeWithFlatPlaylist() {
        assertEquals(
            listOf("-J", "--no-download", "--flat-playlist"),
            buildProbeArgs("https://www.instagram.com/stories/someone/"),
        )
    }
}
