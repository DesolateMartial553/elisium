package com.desolate.elisium.engine

import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val URL_A = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
private const val URL_B = "https://www.youtube.com/watch?v=BaW_jenozKc"
private const val URL_C = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
private const val URL_OTHER = "https://vimeo.com/12345"

private const val PROBE = """{"id": "dQw4w9WgXcQ", "title": "Video", "thumbnail": "https://img.example/t.jpg", "formats": [{"format_id": "18"}]}"""

/** "Faster downloads" in the queue: extract once, one re-run from the link, the 429 rail, steadier numbers (brief 12D). */
@OptIn(ExperimentalCoroutinesApi::class)
class FasterQueueTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private class Rig(scope: CoroutineScope, base: File, concurrency: Int = 2, val now: () -> Long) {
        val history = FakeHistory()
        val backend = FakeBackend()
        val delays = CopyOnWriteArrayList<Long>()
        val queue = DownloadQueue(
            history, Archive(File(base, "data/archive.txt")), FakeStore(), backend, File(base, "staging"), scope,
            delay = { delays.add(it) },
            concurrency = concurrency,
            clock = now,
        )

        init {
            backend.probeHandler = { json(PROBE) }
        }

        suspend fun runAll() {
            queue.start()
            queue.waitUntilIdle()
        }
    }

    private var clockNow = 1_000_000L

    private fun TestScope.rig(concurrency: Int = 2) = Rig(backgroundScope, tmp.root, concurrency) { clockNow }

    /** The info file as each run saw it when it started: (existed, content, permissions). */
    private class Seen(val existed: Boolean, val content: String?, val perms: String?)

    private fun Rig.watchInfoFiles(): CopyOnWriteArrayList<Seen> {
        val seen = CopyOnWriteArrayList<Seen>()
        backend.startHandler = { request, _ ->
            val f = request.infoJson
            seen.add(
                Seen(
                    f?.isFile == true, f?.takeIf { it.isFile }?.readText(),
                    f?.takeIf { it.isFile }?.let { PosixFilePermissions.toString(Files.getPosixFilePermissions(it.toPath())) },
                ),
            )
            FakeHandle().also { it.finish(successOutcome(request)) }
        }
        return seen
    }

    // -- extract once --------------------------------------------------------
    @Test
    fun `auto loads the probe's info from a private file, without the link, and deletes it`() = runTest {
        val r = rig()
        val seen = r.watchInfoFiles()
        r.queue.add(URL_A)
        r.runAll()
        val request = r.backend.requests.single()
        assertNotNull(request.infoJson)
        val s = seen.single()
        assertTrue(s.existed)
        assertEquals(json(PROBE), json(s.content!!))
        assertEquals("rw-------", s.perms)
        assertFalse(request.infoJson!!.exists())
        assertEquals("done", r.queue.items.value.single().state)
    }

    @Test
    fun `off passes no info and the request is the same as before`() = runTest {
        val r = rig()
        r.queue.setReuseProbe(false)
        r.queue.add(URL_A)
        r.runAll()
        val request = r.backend.requests.single()
        assertNull(request.infoJson)
        assertEquals(URL_A, request.url)
    }

    @Test
    fun `an unusable probe is not loaded`() = runTest {
        for (probe in listOf(
            """{"id": "x", "title": "No formats"}""",
            """{"_type": "playlist", "id": "p", "formats": [{"format_id": "1"}]}""",
        )) {
            val r = rig()
            r.backend.probeHandler = { json(probe) }
            r.queue.add(URL_A)
            r.runAll()
            assertNull(probe, r.backend.requests.single().infoJson)
        }
    }

    @Test
    fun `a probe older than five minutes is looked up again`() = runTest {
        // Every clock read moves 200 s on, so the download starts long after the probe returned.
        var t = 0L
        val old = Rig(backgroundScope, tmp.root, 2) { t += 200_000; t }
        old.backend.probeHandler = { json(PROBE) }
        old.queue.add(URL_A)
        old.runAll()
        assertNull(old.backend.requests.single().infoJson)
    }

    @Test
    fun `a 403 on the info run re-runs once from the link, no retry no backoff`() = runTest {
        val r = rig()
        var runs = 0
        r.backend.startHandler = { request, _ ->
            runs++
            FakeHandle().also {
                if (request.infoJson != null) {
                    it.finish(DownloadOutcome(1, "", null, errorLog = "ERROR: unable to download video data: HTTP Error 403: Forbidden"))
                } else {
                    it.finish(successOutcome(request))
                }
            }
        }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals(2, runs)
        assertNotNull(r.backend.requests[0].infoJson)
        assertNull(r.backend.requests[1].infoJson)
        assertEquals(URL_A, r.backend.requests[1].url)
        val item = r.queue.items.value.single()
        assertEquals("done", item.state)
        assertEquals(0, item.attempts)
        assertTrue(r.delays.isEmpty())
        assertFalse(r.backend.requests[0].infoJson!!.exists())
    }

    @Test
    fun `a failure before the first progress line is re-run once, and a failing re-run is final`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("ERROR: something odd")) } }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals(2, r.backend.starts)
        assertEquals("failed", r.queue.items.value.single().state)
        assertTrue(r.delays.isEmpty())
    }

    @Test
    fun `a failure after progress that is not stale is not re-run`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, onProgress ->
            onProgress(Progress("downloading", downloadedBytes = 10, totalBytes = 100, percent = 10.0))
            FakeHandle().also { it.finish(failureOutcome("ERROR: something odd")) }
        }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals(1, r.backend.starts)
        assertEquals("failed", r.queue.items.value.single().state)
    }

    @Test
    fun `a failed run without the saved lookup is never re-run`() = runTest {
        val r = rig()
        r.queue.setReuseProbe(false)
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("ERROR: something odd")) } }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals(1, r.backend.starts)
    }

    @Test
    fun `the info file is removed when the backend throws`() = runTest {
        val r = rig()
        var file: File? = null
        r.backend.startHandler = { request, _ ->
            file = request.infoJson
            throw IllegalStateException("boom")
        }
        r.queue.add(URL_A)
        r.runAll()
        assertNotNull(file)
        assertFalse(file!!.exists())
    }

    // -- the 429 rail ----------------------------------------------------------
    @Test
    fun `after a 429 the site loses probe reuse and runs one at a time, other sites go on`() = runTest {
        val r = rig(concurrency = 3)
        r.queue.setReuseProbe(true)
        // First download of the site is rate limited.
        r.backend.startHandler = { _, _ ->
            FakeHandle().also { it.finish(DownloadOutcome(1, "", null, errorLog = "ERROR: HTTP Error 429: Too Many Requests")) }
        }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals("http_429", r.queue.items.value.single().error?.code)

        // Now three more: two of the limited site, one of another site. Handles stay open until released.
        val handles = CopyOnWriteArrayList<Pair<DownloadRequest, FakeHandle>>()
        r.backend.startHandler = { request, _ -> FakeHandle().also { handles.add(request to it) } }
        r.queue.add(URL_B)
        r.queue.add(URL_C)
        r.queue.add(URL_OTHER)
        runCurrent()
        val running = handles.map { it.first.url }
        assertEquals(setOf(URL_B, URL_OTHER), running.toSet()) // one youtube + the other site, not two youtube
        assertNull(handles.first { it.first.url == URL_B }.first.infoJson) // no reuse for the limited site
        assertNotNull(handles.first { it.first.url == URL_OTHER }.first.infoJson) // other sites keep it
        val waiting = r.queue.items.value.first { it.url == URL_C }
        assertEquals("queued", waiting.state)
        assertEquals(WAIT_RATE_LIMITED, waiting.waitHint)
        assertNull(r.queue.items.value.first { it.url == URL_OTHER }.waitHint)

        // When the running one of the limited site finishes, the next one starts.
        handles.first { it.first.url == URL_B }.let { (req, h) -> h.finish(successOutcome(req)) }
        runCurrent()
        assertTrue(handles.any { it.first.url == URL_C })
    }

    // -- steadier numbers + quiet stamp --------------------------------------------
    @Test
    fun `speed and time left are smoothed after two seconds and a row's quiet stamp follows its progress`() = runTest {
        val r = rig(concurrency = 1)
        var report: ((Progress) -> Unit)? = null
        val handle = FakeHandle()
        r.backend.startHandler = { _, onProgress -> report = onProgress; handle }
        val item = r.queue.add(URL_A)
        r.queue.start()
        runCurrent()
        val send = report!!
        val startedAt = clockNow
        // Warm-up (first 2 s): as reported.
        send(Progress("downloading", downloadedBytes = 1_000, totalBytes = 101_000, speed = 5000.0, eta = 20.0, percent = 1.0))
        assertEquals(5000.0, r.queue.item(item.id)!!.speed!!, 1e-9)
        assertEquals(startedAt, r.queue.item(item.id)!!.quietSince)
        clockNow += 1_000
        send(Progress("downloading", downloadedBytes = 2_000, totalBytes = 101_000, speed = 9000.0, eta = 11.0, percent = 2.0))
        assertEquals(9000.0, r.queue.item(item.id)!!.speed!!, 1e-9)
        // After 2 s the first sample seeds the average, the next one moves it a fifth of the way.
        clockNow += 1_000
        send(Progress("downloading", downloadedBytes = 3_000, totalBytes = 101_000, speed = 1000.0, eta = 98.0, percent = 3.0))
        assertEquals(1000.0, r.queue.item(item.id)!!.speed!!, 1e-9)
        clockNow += 1_000
        send(Progress("downloading", downloadedBytes = 4_000, totalBytes = 101_000, speed = 2000.0, eta = 48.0, percent = 4.0))
        val now = r.queue.item(item.id)!!
        assertEquals(1200.0, now.speed!!, 1e-9)
        assertEquals((101_000 - 4_000) / 1200.0, now.eta!!, 1e-9)
        assertEquals(clockNow, now.quietSince)
        // No new bytes: the stamp stays where it was.
        val stamp = now.quietSince
        clockNow += 5_000
        send(Progress("downloading", downloadedBytes = 4_000, totalBytes = 101_000, speed = 2000.0, eta = 48.0, percent = 4.0))
        assertEquals(stamp, r.queue.item(item.id)!!.quietSince)
        handle.finish(successOutcome(r.backend.requests.single()))
        r.queue.waitUntilIdle()
    }

    // -- verified, pinned ---------------------------------------------------------------
    @Test
    fun `the thumbnail is shown as soon as the probe returns, before the download starts`() = runTest {
        val r = rig()
        val events = CopyOnWriteArrayList<QueueEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { r.queue.events.collect { events.add(it) } }
        var seenAtStart: String? = null
        r.backend.startHandler = { request, _ ->
            seenAtStart = events.filterIsInstance<QueueEvent.ItemUpdated>().lastOrNull()?.item?.thumbnail
            FakeHandle().also { it.finish(successOutcome(request)) }
        }
        r.queue.add(URL_A)
        r.runAll()
        assertEquals("https://img.example/t.jpg", seenAtStart)
    }

    @Test
    fun `the aria2c downloader is never asked for`() = runTest {
        val r = rig()
        r.queue.add(URL_A)
        r.runAll()
        val request = r.backend.requests.single()
        assertFalse(request.extraArgs.any { "aria2" in it || it == "--downloader" || it == "--external-downloader" })
    }
}
