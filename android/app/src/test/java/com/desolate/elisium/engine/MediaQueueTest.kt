package com.desolate.elisium.engine

import com.desolate.elisium.media.CancelToken
import com.desolate.elisium.media.FakeFfmpeg
import com.desolate.elisium.media.FfmpegSession
import com.desolate.elisium.media.FileDownloader
import com.desolate.elisium.media.FULL_SONG_NOTE
import com.desolate.elisium.media.MIX_FAILED_NOTE
import com.desolate.elisium.media.MediaEngine
import com.desolate.elisium.media.MediaFailure
import com.desolate.elisium.media.MediaFetchException
import com.desolate.elisium.media.MediaFetcher
import com.desolate.elisium.media.MediaItem
import com.desolate.elisium.media.MediaKind
import com.desolate.elisium.media.MediaPost
import com.desolate.elisium.media.MusicClip
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val POST_URL = "https://www.instagram.com/p/BEiEPR96YEV/"
private const val REEL_URL = "https://www.instagram.com/reel/CreelCode1/"
private const val TRAY_URL = "https://www.instagram.com/stories/example_user/"
private const val HIGHLIGHT_URL = "https://www.instagram.com/stories/highlights/17900000000000001/"
private const val STORY_URL = "https://www.instagram.com/stories/example_user/3222222222222222201/"
private const val TIKTOK_URL = "https://www.tiktok.com/@dancer/photo/7300000000000000001"
private const val TIKTOK_VIDEO_URL = "https://www.tiktok.com/@dancer/video/7300000000000000002"
private const val NO_VIDEO = "ERROR: [Instagram] BEiEPR96YEV: There is no video in this post"
private const val SECRET = "SESSION-SECRET-VALUE-123"

private fun item(n: Int, id: String = "3111111111111111$n"): MediaItem =
    MediaItem(MediaKind.IMAGE, "https://cdn.example.com/p/$n.jpg", 1080, 1350, n, id, "jpg")

private val SONG = MusicClip("https://cdn.example.com/a/song.m4a", "Song", "Artist", startMs = 15400, durationMs = 15000)

private fun carousel(photos: Int = 3, music: MusicClip? = SONG, id: String = "CmadeUp0003") = MediaPost(
    site = "instagram", id = id, owner = "example_user", takenAt = 1701000200L, caption = "A made-up carousel\nsecond line",
    items = (1..photos).map { item(it) }, music = music,
)

private const val BASE = "example_user 2023-11-26 CmadeUp0003"
private fun slideName(n: Int) = "$BASE [3111111111111111$n] $n.jpg"
private const val SONG_NAME = "$BASE song [CmadeUp0003_song].m4a"
private const val MIX_NAME = "$BASE [CmadeUp0003_mix].mp4"

class FakeFetcher : MediaFetcher {
    var handler: (String) -> List<MediaPost> = { listOf(carousel()) }
    val calls = CopyOnWriteArrayList<String>()
    val cookies = CopyOnWriteArrayList<File?>()

    override fun fetch(url: String, cookiesFile: File?, token: CancelToken): List<MediaPost> {
        calls.add(url)
        cookies.add(cookiesFile)
        return handler(url)
    }
}

class FakeDownloader : FileDownloader {
    val urls = CopyOnWriteArrayList<String>()
    var failUrls = mutableSetOf<String>()
    var failOnce = mutableSetOf<String>()
    var failWith = MediaFailure.NETWORK
    var onDownload: (Int, String) -> Unit = { _, _ -> }

    override fun download(url: String, target: File, token: CancelToken) {
        urls.add(url)
        onDownload(urls.size, url)
        if (token.cancelled) return
        if (failOnce.remove(url)) throw MediaFetchException(failWith, "HTTP fail once")
        if (url in failUrls) throw MediaFetchException(failWith, "HTTP fail")
        target.parentFile?.mkdirs()
        target.writeText("bytes:$url")
    }
}

/** Owner folders without a device: remembers which names went where. */
class FolderStore : OutputStore {
    val saved = LinkedHashMap<String, String?>() // file name -> owner folder
    val flatPublishes = CopyOnWriteArrayList<String>()

    override fun existsFor(extractorKey: String, videoId: String): Boolean = false
    override fun existsAt(location: String): Boolean = saved.any { (n, s) -> location == loc(s, n) }
    override suspend fun publish(stagedFile: File, displayName: String): PublishedFile? {
        flatPublishes.add(displayName)
        return publish(stagedFile, displayName, null)
    }

    override suspend fun publish(stagedFile: File, displayName: String, subfolder: String?): PublishedFile? {
        saved[displayName] = subfolder
        stagedFile.delete()
        return PublishedFile(loc(subfolder, displayName), displayName)
    }

    override fun existsInFolder(subfolder: String?, videoId: String): Boolean =
        saved.any { (n, s) -> s == subfolder && "[$videoId]" in n }

    override fun forget(extractorKey: String, videoId: String) = Unit

    fun loc(sub: String?, name: String) = "store://${sub ?: ""}/$name"
    fun names(): List<String> = saved.keys.sorted()
    fun deleteMatching(text: String) {
        saved.keys.filter { text in it }.forEach { saved.remove(it) }
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
private class MRig(
    scope: CoroutineScope,
    base: File,
    val store: FolderStore = FolderStore(),
    ffmpegAvailable: Boolean = true,
    withEngine: Boolean = true,
) {
    val history = FakeHistory()
    val backend = FakeBackend()
    val fetcher = FakeFetcher()
    val downloader = FakeDownloader()
    val sessions = CopyOnWriteArrayList<FakeFfmpeg>()
    val delays = CopyOnWriteArrayList<Long>()
    val archive = Archive(File(base, "data/archive.txt"))
    val mediaArchiveFile = File(base, "data/media-archive.txt")
    val staging = File(base, "staging")
    val queue = DownloadQueue(
        history, archive, store, backend, staging, scope,
        delay = { ms -> delays.add(ms); kotlinx.coroutines.delay(ms) },
    )

    init {
        if (withEngine) {
            queue.setMediaEngine(
                MediaEngine(fetcher, downloader, ffmpeg = {
                    if (ffmpegAvailable) FakeFfmpeg().also { sessions.add(it) } else null
                }),
            )
        }
    }

    suspend fun runAll() {
        queue.start()
        queue.waitUntilIdle()
    }

    fun states(item: QueueItem) = history.stateLog.filter { it.first == item.recordId }.map { it.second }
}

@OptIn(ExperimentalCoroutinesApi::class)
class MediaQueueTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun TestScope.rig(
        store: FolderStore = FolderStore(),
        ffmpeg: Boolean = true,
        engine: Boolean = true,
    ) = MRig(backgroundScope, tmp.root, store, ffmpeg, engine)

    private fun TestScope.collect(queue: DownloadQueue): CopyOnWriteArrayList<QueueEvent> {
        val seen = CopyOnWriteArrayList<QueueEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { queue.events.collect { seen.add(it) } }
        return seen
    }

    private fun noVideo(r: MRig) {
        r.backend.probeHandler = { throw ProbeFailure(NO_VIDEO) }
    }

    // -- routing -----------------------------------------------------------------
    @Test
    fun `reels and video links stay on yt-dlp`() = runTest {
        for (url in listOf(REEL_URL, TIKTOK_VIDEO_URL, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")) {
            val r = rig()
            r.queue.add(url)
            r.runAll()
            assertEquals(url, 1, r.backend.starts)
            assertTrue(url, r.fetcher.calls.isEmpty())
        }
    }

    @Test
    fun `story trays, highlights and tiktok photo posts go straight to the media engine`() = runTest {
        for (url in listOf(TRAY_URL, HIGHLIGHT_URL, TIKTOK_URL)) {
            val r = rig()
            val queued = r.queue.add(url)
            r.runAll()
            assertTrue(url, r.backend.probes.isEmpty())
            assertEquals(url, 0, r.backend.starts)
            assertEquals(url, listOf(url), r.fetcher.calls.toList().map { it })
            assertEquals(url, "done", r.queue.item(queued.id)!!.state)
        }
    }

    @Test
    fun `an instagram post and a single story try yt-dlp first and keep it when it works`() = runTest {
        for (url in listOf(POST_URL, STORY_URL)) {
            val r = rig()
            r.queue.add(url)
            r.runAll()
            assertEquals(url, 1, r.backend.starts)
            assertTrue(url, r.fetcher.calls.isEmpty())
        }
    }

    @Test
    fun `without a media engine nothing is rerouted`() = runTest {
        val r = rig(engine = false)
        val queued = r.queue.add(TRAY_URL)
        r.runAll()
        assertEquals(1, r.backend.probes.size)
        assertTrue(r.fetcher.calls.isEmpty())
        assertEquals("done", r.queue.item(queued.id)!!.state)
    }

    // -- the /p/ fallback -----------------------------------------------------------
    @Test
    fun `a post yt-dlp has no video for is retried once on the media engine without counting a retry`() = runTest {
        val r = rig()
        noVideo(r)
        val queued = r.queue.add(POST_URL)
        r.runAll()
        val done = r.queue.item(queued.id)!!
        assertEquals("done", done.state)
        assertEquals(0, done.attempts)
        assertTrue(r.delays.isEmpty())
        assertEquals(1, r.backend.probes.size)
        assertEquals(1, r.fetcher.calls.size)
        assertEquals(listOf("probing", "downloading", "converting", "done"), r.states(queued))
        assertEquals("A made-up carousel", done.title)
        assertEquals("3 photos + song", done.formatLabel)
        assertEquals("https://cdn.example.com/p/1.jpg", done.thumbnail)
    }

    @Test
    fun `no_media at download time falls back too, through probing again`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome(NO_VIDEO)) } }
        val queued = r.queue.add(POST_URL)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        assertEquals(0, r.queue.item(queued.id)!!.attempts)
        assertEquals(listOf("probing", "downloading", "probing", "downloading", "converting", "done"), r.states(queued))
        assertEquals(1, r.backend.starts)
    }

    @Test
    fun `the media engine's own no_media is final and never goes back to yt-dlp`() = runTest {
        val r = rig()
        noVideo(r)
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.NO_MEDIA) }
        val queued = r.queue.add(POST_URL)
        r.runAll()
        val failed = r.queue.item(queued.id)!!
        assertEquals("failed", failed.state)
        assertEquals("no_media", failed.error!!.code)
        assertEquals("There are no photos or videos to download here.", failed.error!!.message)
        assertEquals(1, r.backend.probes.size)
        assertEquals(1, r.fetcher.calls.size)
        assertTrue(r.delays.isEmpty())
    }

    @Test
    fun `a media failure after the fallback retries on the media engine, not yt-dlp`() = runTest {
        val r = rig()
        noVideo(r)
        var calls = 0
        r.fetcher.handler = { if (++calls == 1) throw MediaFetchException(MediaFailure.NETWORK) else listOf(carousel()) }
        val queued = r.queue.add(POST_URL)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        assertEquals(1, r.backend.probes.size) // the second attempt did not ask yt-dlp again
        assertEquals(2, r.fetcher.calls.size)
        assertEquals(listOf(5_000L), r.delays.toList())
        assertEquals(1, r.queue.item(queued.id)!!.attempts)
    }

    @Test
    fun `a single story with no video falls back and keeps only that story`() = runTest {
        val r = rig()
        noVideo(r)
        val story = { id: String ->
            MediaPost("instagram", id, "example_user", 1701000500L, null, listOf(item(1, id)), null)
        }
        r.fetcher.handler = { listOf(story("3222222222222222200"), story("3222222222222222201")) }
        val queued = r.queue.add(STORY_URL)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        assertEquals(1, r.downloader.urls.size)
        assertEquals(1, r.queue.item(queued.id)!!.filesTotal)
    }

    @Test
    fun `a single story that is gone is expired`() = runTest {
        val r = rig()
        r.fetcher.handler = { listOf(MediaPost("instagram", "999", "u", null, null, listOf(item(1, "999")), null)) }
        val queued = r.queue.add("https://www.instagram.com/stories/example_user/3222222222222222201/")
        r.backend.probeHandler = { throw ProbeFailure(NO_VIDEO) }
        r.runAll()
        val failed = r.queue.item(queued.id)!!
        assertEquals("story_expired", failed.error!!.code)
    }

    // -- files, progress, naming ----------------------------------------------------
    @Test
    fun `a carousel with a song is saved under the owner with the desktop names and counted per file`() = runTest {
        val r = rig()
        val events = collect(r.queue)
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        val done = r.queue.item(queued.id)!!
        assertEquals("done", done.state)
        assertEquals(listOf(slideName(1), slideName(2), slideName(3), SONG_NAME, MIX_NAME).sorted(), r.store.names())
        assertTrue(r.store.saved.values.all { it == "example_user" })
        assertTrue(r.store.flatPublishes.isEmpty()) // everything went through the owner-folder seam
        assertEquals(5, done.filesTotal)
        assertEquals(5, done.filesDone)
        assertEquals(100.0, done.percent!!, 0.0)
        assertNull(done.note)
        assertEquals("store://example_user/${r.store.names().first()}", done.filePath)
        val progress = events.filterIsInstance<QueueEvent.ProgressChanged>().map { it.item.filesDone }
        assertEquals(listOf(1, 2, 3, 4), progress)
        assertEquals(listOf(20.0, 40.0, 60.0, 80.0), events.filterIsInstance<QueueEvent.ProgressChanged>().map { it.item.percent })
        // history carries the count and note
        assertEquals(5, r.history.get(done.recordId)!!.filesTotal)
        // the keys live in the media archive, not the yt-dlp one
        val keys = r.mediaArchiveFile.readText().lines().filter { it.isNotBlank() }.toSet()
        assertEquals(
            setOf("instagram 31111111111111111", "instagram 31111111111111112", "instagram 31111111111111113",
                "instagram CmadeUp0003_song", "instagram CmadeUp0003_mix"),
            keys,
        )
        assertFalse(r.archive.file.exists())
        // the staging folder is cleaned up
        assertFalse(File(r.staging, "media").walkTopDown().any { it.isFile })
    }

    @Test
    fun `the song is cut from the post's snippet and the mix is built with ffmpeg`() = runTest {
        val r = rig()
        r.queue.add(TIKTOK_URL)
        r.runAll()
        val argv = r.sessions.single().runs
        assertEquals(2, argv.size)
        assertEquals("15.400", argv[0][argv[0].indexOf("-ss") + 1])
        assertTrue("-filter_complex" in argv[1])
    }

    @Test
    fun `tiktok slideshows use the tiktok names`() = runTest {
        val r = rig()
        r.fetcher.handler = {
            listOf(
                MediaPost(
                    "tiktok", "7300000000000000001", "dancer", 1702000000L, "cap",
                    listOf(
                        MediaItem(MediaKind.IMAGE, "https://cdn.example.com/t/1.jpeg", 1080, 1440, 1, "7300000000000000001_1", "jpg"),
                        MediaItem(MediaKind.IMAGE, "https://cdn.example.com/t/2.jpeg", 720, 960, 2, "7300000000000000001_2", "jpg"),
                    ),
                    MusicClip("https://cdn.example.com/t/sound.mp3", "S", "A"),
                ),
            )
        }
        r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(
            listOf(
                "dancer 7300000000000000001 [7300000000000000001_1] 1.jpg",
                "dancer 7300000000000000001 [7300000000000000001_2] 2.jpg",
                "dancer 7300000000000000001 [7300000000000000001_mix].mp4",
                "dancer 7300000000000000001 song [7300000000000000001_song].mp3",
            ).sorted(),
            r.store.names(),
        )
        // a tiktok sound has no snippet times: the whole song stays, with the desktop note
        assertEquals(FULL_SONG_NOTE, r.queue.item(1)!!.note)
    }

    // -- the archive and "Already saved" ---------------------------------------------
    @Test
    fun `adding the same post again in a new session saves nothing and says Already saved`() = runTest {
        val store = FolderStore()
        val first = rig(store)
        first.queue.add(TIKTOK_URL)
        first.runAll()
        val savedBefore = store.names()

        val again = rig(store)
        val queued = again.queue.add(TIKTOK_URL)
        again.runAll()
        val item = again.queue.item(queued.id)!!
        assertEquals("skipped", item.state)
        assertEquals("already_downloaded", item.error!!.code)
        assertEquals("Already saved", item.note)
        assertEquals(0, again.downloader.urls.size) // nothing was fetched again
        assertEquals(savedBefore, store.names())
        assertEquals("Already saved", again.history.get(item.recordId)!!.note)
    }

    @Test
    fun `a post with one missing file only fetches that file`() = runTest {
        val store = FolderStore()
        val first = rig(store)
        first.queue.add(TIKTOK_URL)
        first.runAll()
        store.deleteMatching("[31111111111111112]")

        val again = rig(store)
        val queued = again.queue.add(TIKTOK_URL)
        again.runAll()
        val item = again.queue.item(queued.id)!!
        assertEquals("done", item.state)
        assertEquals(listOf("https://cdn.example.com/p/2.jpg"), again.downloader.urls.toList())
        assertTrue(store.names().contains(slideName(2)))
        assertEquals(5, store.names().size)
    }

    @Test
    fun `a file that is in the archive but gone is fetched again and the stale key replaced`() = runTest {
        val store = FolderStore()
        val first = rig(store)
        first.queue.add(TIKTOK_URL)
        first.runAll()
        store.deleteMatching("song")
        val again = rig(store)
        again.queue.add(TIKTOK_URL)
        again.runAll()
        assertTrue(store.names().contains(SONG_NAME))
        assertTrue(again.mediaArchiveFile.readText().contains("instagram CmadeUp0003_song"))
    }

    @Test
    fun `Download again anyway ignores the archive for that run`() = runTest {
        val store = FolderStore()
        val first = rig(store)
        first.queue.add(TIKTOK_URL)
        first.runAll()

        val forced = rig(store)
        val queued = forced.queue.add(TIKTOK_URL, force = true)
        forced.runAll()
        val item = forced.queue.item(queued.id)!!
        assertEquals(4, forced.downloader.urls.size) // 3 photos and the song were requested again
        assertEquals("skipped", item.state) // same names were already there: never renamed or duplicated
        assertEquals("Already saved", item.note)
        assertEquals(5, store.names().size)
    }

    @Test
    fun `force on the same queue requeues a finished item and runs it again`() = runTest {
        val r = rig()
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        val before = r.downloader.urls.size
        val same = r.queue.add(TIKTOK_URL, force = true)
        assertEquals(queued.id, same.id)
        assertEquals("queued", r.queue.item(queued.id)!!.state)
        r.runAll()
        assertEquals(before * 2, r.downloader.urls.size)
        assertEquals("skipped", r.queue.item(queued.id)!!.state)
    }

    @Test
    fun `force is ignored for plain yt-dlp links`() = runTest {
        val r = rig()
        val queued = r.queue.add(REEL_URL, force = true)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        r.queue.add(REEL_URL, force = true)
        assertEquals("done", r.queue.item(queued.id)!!.state) // not requeued
    }

    // -- errors -----------------------------------------------------------------------
    private fun failWith(failure: MediaFailure, url: String = TIKTOK_URL, cookies: Boolean = false): ErrorInfo {
        var result: ErrorInfo? = null
        runTest {
            val r = rig()
            r.fetcher.handler = { throw MediaFetchException(failure) }
            if (cookies) r.queue.setCookiesFile(tmp.newFile("c${System.nanoTime()}.txt").apply { writeText("x") })
            val queued = r.queue.add(url)
            r.runAll()
            result = r.queue.item(queued.id)!!.error
            assertEquals("failed", r.queue.item(queued.id)!!.state)
        }
        return result!!
    }

    @Test
    fun `every failure becomes the desktop words on the item`() {
        assertEquals("login_required", failWith(MediaFailure.LOGIN_REQUIRED, TRAY_URL).code)
        assertEquals("session_expired", failWith(MediaFailure.LOGIN_REQUIRED, TRAY_URL, cookies = true).code)
        assertEquals("rate_limited", failWith(MediaFailure.RATE_LIMITED, HIGHLIGHT_URL).code)
        assertEquals("story_expired", failWith(MediaFailure.NO_MEDIA, TRAY_URL).code)
        assertEquals("story_expired", failWith(MediaFailure.NOT_FOUND, TRAY_URL).code)
        assertEquals("private_account", failWith(MediaFailure.PRIVATE, TRAY_URL, cookies = true).code)
        assertEquals("video_unavailable", failWith(MediaFailure.NOT_FOUND, TIKTOK_URL).code)
        assertEquals("no_media", failWith(MediaFailure.NO_MEDIA, TIKTOK_URL).code)
        assertEquals("unknown", failWith(MediaFailure.UNKNOWN, TIKTOK_URL).code)
        val tiktokLogin = failWith(MediaFailure.LOGIN_REQUIRED, TIKTOK_URL, cookies = true)
        assertEquals("The site wants you to be signed in.", tiktokLogin.message)
    }

    @Test
    fun `network problems retry with the 5 15 45 second backoff, then fail`() = runTest {
        val r = rig()
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.NETWORK) }
        val queued = r.queue.add(TRAY_URL)
        r.runAll()
        val failed = r.queue.item(queued.id)!!
        assertEquals("failed", failed.state)
        assertEquals("network", failed.error!!.code)
        assertEquals(listOf(5_000L, 15_000L, 45_000L), r.delays.toList())
        assertEquals(4, r.fetcher.calls.size)
    }

    @Test
    fun `a failure that cannot be retried clears the staging folder and a manual retry starts clean`() = runTest {
        val r = rig()
        r.downloader.failUrls.add("https://cdn.example.com/p/3.jpg")
        r.downloader.failWith = MediaFailure.NOT_FOUND
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals("failed", r.queue.item(queued.id)!!.state)
        assertTrue(r.store.names().isEmpty()) // nothing was moved
        assertFalse(File(r.staging, "media").walkTopDown().any { it.isFile })
        r.downloader.failUrls.clear()
        r.queue.retry(queued.id)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
    }

    @Test
    fun `a retryable failure keeps staged files so the retry skips them`() = runTest {
        val r = rig()
        r.downloader.failOnce.add("https://cdn.example.com/p/3.jpg")
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(listOf(5_000L), r.delays.toList())
        val item = r.queue.item(queued.id)!!
        assertEquals("done", item.state)
        // photo 3 failed once, then everything before it was kept: 1,2 fetched once; 3 twice; song once
        assertEquals(1, r.downloader.urls.count { it.endsWith("1.jpg") })
        assertEquals(1, r.downloader.urls.count { it.endsWith("2.jpg") })
        assertEquals(2, r.downloader.urls.count { it.endsWith("3.jpg") })
    }

    @Test
    fun `the session never shows up in an error, a note or the history`() = runTest {
        val r = rig()
        val cookies = tmp.newFile("cookies.txt").apply { writeText(".instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\t$SECRET\n") }
        r.queue.setCookiesFile(cookies)
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP 401") }
        val queued = r.queue.add(TRAY_URL)
        r.runAll()
        val item = r.queue.item(queued.id)!!
        assertEquals(cookies, r.fetcher.cookies.single()) // only the path was handed over
        assertEquals("session_expired", item.error!!.code)
        val row = r.history.get(item.recordId)!!
        val everything = listOf(item.toString(), row.toString())
        assertTrue(everything.none { SECRET in it })
        assertFalse(row.toString().contains("cookies.txt"))
    }

    // -- settings -----------------------------------------------------------------------
    @Test
    fun `missing ffmpeg is done with the desktop note`() = runTest {
        val r = rig(ffmpeg = false)
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        val item = r.queue.item(queued.id)!!
        assertEquals("done", item.state)
        assertEquals("Kept the full song: it couldn't be trimmed. $MIX_FAILED_NOTE", item.note)
        assertEquals(4, item.filesTotal) // no mp4 was expected
        assertEquals(listOf(slideName(1), slideName(2), slideName(3), SONG_NAME).sorted(), r.store.names())
    }

    @Test
    fun `every photo mode and song length combination`() = runTest {
        val photos = (1..3).map(::slideName)
        data class Expect(val names: List<String>, val total: Int, val ffmpegRuns: Int)
        val table = mapOf(
            (PhotoMode.PhotosSongVideo to SongLength.Snippet) to Expect(photos + SONG_NAME + MIX_NAME, 5, 2),
            (PhotoMode.PhotosSongVideo to SongLength.Full) to Expect(photos + SONG_NAME + MIX_NAME, 5, 1),
            (PhotoMode.PhotosSong to SongLength.Snippet) to Expect(photos + SONG_NAME, 4, 1),
            (PhotoMode.PhotosSong to SongLength.Full) to Expect(photos + SONG_NAME, 4, 0),
            (PhotoMode.PhotosOnly to SongLength.Snippet) to Expect(photos, 3, 0),
            (PhotoMode.PhotosOnly to SongLength.Full) to Expect(photos, 3, 0),
        )
        assertEquals(PhotoMode.entries.size * SongLength.entries.size, table.size)
        for ((combo, expected) in table) {
            val r = MRig(backgroundScope, tmp.newFolder(), FolderStore(), true, true)
            r.queue.setPhotoMode(combo.first)
            r.queue.setSongLength(combo.second)
            val queued = r.queue.add(TIKTOK_URL)
            r.runAll()
            val item = r.queue.item(queued.id)!!
            assertEquals("$combo", "done", item.state)
            assertEquals("$combo", expected.names.sorted(), r.store.names())
            assertEquals("$combo", expected.total, item.filesTotal)
            assertEquals("$combo", expected.ffmpegRuns, r.sessions.sumOf { it.runs.size })
            assertNull("$combo", item.note)
        }
    }

    @Test
    fun `without ffmpeg a re-add fetches nothing and says Already saved`() = runTest {
        val store = FolderStore()
        val first = rig(store, ffmpeg = false)
        first.queue.add(TIKTOK_URL)
        first.runAll()
        assertEquals(4, store.names().size) // photos and song, no video

        val again = rig(store, ffmpeg = false)
        val queued = again.queue.add(TIKTOK_URL)
        again.runAll()
        val item = again.queue.item(queued.id)!!
        assertTrue(again.downloader.urls.isEmpty())
        assertEquals("skipped", item.state)
        assertEquals("Already saved", item.note)
        assertEquals(4, store.names().size)
    }

    @Test
    fun `a yt-dlp probe gives the card a picture and a kind line`() = runTest {
        val r = rig()
        r.backend.probeHandler = {
            json("""{"id": "x", "title": "T", "thumbnail": "https://i.example.com/t.jpg", "ext": "mp4", "height": 1080}""")
        }
        val queued = r.queue.add(REEL_URL)
        r.runAll()
        val item = r.queue.item(queued.id)!!
        assertEquals("https://i.example.com/t.jpg", item.thumbnail)
        assertEquals("1080p MP4", item.formatLabel)
        assertNull(item.filesTotal)
        assertNull(item.note)

        val audio = rig()
        audio.backend.probeHandler = { json("""{"id": "y", "title": "T", "thumbnail": "ftp://nope"}""") }
        val q2 = audio.queue.add(TIKTOK_VIDEO_URL, extraArgs = listOf("-x", "--audio-format", "mp3"))
        audio.runAll()
        assertNull(audio.queue.item(q2.id)!!.thumbnail)
        assertEquals("MP3 audio", audio.queue.item(q2.id)!!.formatLabel)
    }

    @Test
    fun `photos, song and video is the default setting`() = runTest {
        val r = rig()
        r.queue.add(TIKTOK_URL)
        r.runAll()
        assertTrue(r.store.names().contains(MIX_NAME))
        assertTrue(r.store.names().contains(SONG_NAME))
    }

    @Test
    fun `photos and song builds no video`() = runTest {
        val r = rig()
        r.queue.setPhotoMode(PhotoMode.PhotosSong)
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(listOf(slideName(1), slideName(2), slideName(3), SONG_NAME).sorted(), r.store.names())
        assertEquals(4, r.queue.item(queued.id)!!.filesTotal)
        assertEquals(1, r.sessions.single().runs.size) // the cut only
    }

    @Test
    fun `photos only never fetches the song`() = runTest {
        val r = rig()
        r.queue.setPhotoMode(PhotoMode.PhotosOnly)
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(listOf(slideName(1), slideName(2), slideName(3)), r.store.names())
        assertEquals(3, r.queue.item(queued.id)!!.filesTotal)
        assertFalse(r.downloader.urls.any { it.contains("song") })
        assertEquals("3 photos", r.queue.item(queued.id)!!.formatLabel)
    }

    @Test
    fun `full song skips the cut and keeps the whole track without a note`() = runTest {
        val r = rig()
        r.queue.setSongLength(SongLength.Full)
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(1, r.sessions.single().runs.size) // the mix only
        assertNull(r.queue.item(queued.id)!!.note)
        assertTrue(r.store.names().contains(SONG_NAME))
    }

    @Test
    fun `a photo post without a song is photos only whatever the setting`() = runTest {
        val r = rig()
        r.fetcher.handler = { listOf(carousel(music = null)) }
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        assertEquals(3, r.store.names().size)
        assertEquals(3, r.queue.item(queued.id)!!.filesTotal)
        assertTrue(r.sessions.all { it.runs.isEmpty() })
    }

    @Test
    fun `a video already saved is not built again and the missing photos are fetched only for it`() = runTest {
        val store = FolderStore()
        val first = rig(store)
        first.queue.setPhotoMode(PhotoMode.PhotosSong)
        first.queue.add(TIKTOK_URL)
        first.runAll()
        assertFalse(store.names().contains(MIX_NAME))

        // The user switches to "photos, song and video": the mp4 is built from re-fetched photos, nothing else is saved twice.
        val second = rig(store)
        val queued = second.queue.add(TIKTOK_URL)
        second.runAll()
        assertEquals("done", second.queue.item(queued.id)!!.state)
        assertTrue(store.names().contains(MIX_NAME))
        assertEquals(5, store.names().size)
    }

    // -- trays ---------------------------------------------------------------------------------
    @Test
    fun `a story tray is one card with every story, each song kept whole, and no video`() = runTest {
        val r = rig()
        val story = { n: Int ->
            MediaPost("instagram", "32222222222222222$n", "example_user", 1701000500L + n, null, listOf(item(1, "32222222222222222$n")), SONG)
        }
        r.fetcher.handler = { listOf(story(1), story(2)) }
        val queued = r.queue.add(TRAY_URL)
        r.runAll()
        val done = r.queue.item(queued.id)!!
        assertEquals("done", done.state)
        assertEquals(4, done.filesTotal) // 2 stories + 2 songs
        assertEquals(1, r.queue.items.value.size)
        assertEquals(4, r.store.names().size)
        assertTrue(r.store.names().none { it.endsWith(".mp4") })
        assertTrue(r.sessions.all { it.runs.isEmpty() }) // no cutting, no mixing
        assertTrue(r.store.saved.values.all { it == "example_user" })
    }

    // -- pause, cancel, cleanup -------------------------------------------------------------
    @Test
    fun `pausing during a download stops it, keeps the finished files, and a resume skips them`() = runTest {
        val r = rig()
        val queued = r.queue.add(TIKTOK_URL)
        r.downloader.onDownload = { n, _ -> if (n == 3) r.queue.pause(queued.id) }
        r.runAll()
        assertEquals("paused", r.queue.item(queued.id)!!.state)
        assertTrue(r.store.names().isEmpty())
        val staged = File(r.staging, "media").walkTopDown().filter { it.isFile }.map { it.name }.toList()
        assertEquals(2, staged.size) // photos 1 and 2 finished before the pause

        r.downloader.onDownload = { _, _ -> }
        r.queue.resume(queued.id)
        r.runAll()
        assertEquals("done", r.queue.item(queued.id)!!.state)
        assertEquals(1, r.downloader.urls.count { it.endsWith("1.jpg") }) // not fetched again
        assertEquals(1, r.downloader.urls.count { it.endsWith("2.jpg") })
        assertEquals(5, r.store.names().size)
    }

    @Test
    fun `cancelling deletes the item's staging folder`() = runTest {
        val r = rig()
        val queued = r.queue.add(TIKTOK_URL)
        r.downloader.onDownload = { n, _ -> if (n == 3) r.queue.cancel(queued.id) }
        r.runAll()
        assertEquals("cancelled", r.queue.item(queued.id)!!.state)
        assertFalse(File(r.staging, "media").walkTopDown().any { it.isFile })
        assertTrue(r.store.names().isEmpty())
    }

    @Test
    fun `the media folder is per link and old media files are swept`() {
        val staging = tmp.newFolder("staging2")
        val a = mediaDirFor(staging, "instagram:AAA")
        val b = mediaDirFor(staging, "instagram:BBB")
        assertTrue(a != b)
        assertEquals(a, mediaDirFor(staging, "instagram:AAA"))
        assertEquals(staging.path + "/media", a.parentFile.path)
        a.mkdirs()
        val old = File(a, "old.jpg").apply { writeText("x"); setLastModified(1_000L) }
        val fresh = File(a, "fresh.jpg").apply { writeText("x") }
        b.mkdirs()
        File(b, "gone.jpg").apply { writeText("x"); setLastModified(1_000L) }
        val swept = sweepOrphans(staging, ORPHAN_MAX_AGE_MS)
        assertEquals(2, swept)
        assertFalse(old.exists())
        assertTrue(fresh.exists())
        assertFalse(b.exists()) // an emptied folder goes too
        assertTrue(deleteDirectory(a))
        assertFalse(a.exists())
    }

    @Test
    fun `queue items expose thumbnail, format label, files and note`() = runTest {
        val r = rig()
        val queued = r.queue.add(TIKTOK_URL)
        r.runAll()
        val item = r.queue.item(queued.id)!!
        assertNotNull(item.thumbnail)
        assertEquals("3 photos + song", item.formatLabel)
        assertEquals(item.filesTotal, item.filesDone)
    }
}
