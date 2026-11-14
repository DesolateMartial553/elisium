package com.desolate.elisium.engine

import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val VIDEO_ID = "dQw4w9WgXcQ"
private const val URL = "https://www.youtube.com/watch?v=$VIDEO_ID"
private const val VIDEO_ID_2 = "BaW_jenozKc"
private const val URL_2 = "https://www.youtube.com/watch?v=$VIDEO_ID_2"

/** Everything one queue test needs, wired to fakes. */
@OptIn(ExperimentalCoroutinesApi::class)
private class Rig(
    scope: CoroutineScope,
    base: File,
    concurrency: Int = 2,
    archive: Archive? = null,
    val store: FakeStore = FakeStore(),
    delayFn: suspend (Long) -> Unit = { kotlinx.coroutines.delay(it) },
) {
    val history = FakeHistory()
    val backend = FakeBackend()
    val delays = CopyOnWriteArrayList<Long>()
    val archive: Archive = archive ?: Archive(File(base, "data/archive.txt"))
    val staging = File(base, "staging")
    val queue = DownloadQueue(
        history, this.archive, store, backend, staging, scope,
        delay = { ms ->
            delays.add(ms)
            delayFn(ms)
        },
        concurrency = concurrency,
    )

    fun row(item: QueueItem) = history.get(item.recordId)!!

    suspend fun runAll() {
        queue.start()
        queue.waitUntilIdle()
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class DownloadQueueTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun TestScope.rig(concurrency: Int = 2, archive: Archive? = null, store: FakeStore = FakeStore()) =
        Rig(backgroundScope, tmp.root, concurrency, archive, store)

    private fun TestScope.collect(queue: DownloadQueue): CopyOnWriteArrayList<QueueEvent> {
        val seen = CopyOnWriteArrayList<QueueEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { queue.events.collect { seen.add(it) } }
        return seen
    }

    private fun expectIllegal(block: () -> Unit) {
        try {
            block()
            fail("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }

    private fun List<QueueEvent>.states(): List<String> =
        filterIsInstance<QueueEvent.StateChanged>().map { it.state }

    // -- add + dedupe --------------------------------------------------------
    @Test
    fun `add queues one item`() = runTest {
        val r = rig()
        val item = r.queue.add(URL)
        assertEquals("queued", item.state)
        assertEquals("youtube:$VIDEO_ID", item.identity)
        assertEquals("queued", r.row(item).state)
    }

    @Test
    fun `duplicate add returns the same item`() = runTest {
        val r = rig()
        val first = r.queue.add(URL)
        val second = r.queue.add("https://youtu.be/$VIDEO_ID?si=tracking&t=30")
        assertEquals(first.id, second.id)
        assertEquals(1, r.queue.items.value.size)
        assertEquals(1, r.history.recent().size)
    }

    @Test
    fun `non youtube sites dedupe by normalized url`() = runTest {
        val r = rig()
        val first = r.queue.add("https://vimeo.com/12345?utm_source=x#t=1")
        val second = r.queue.add("https://vimeo.com/12345")
        assertEquals(first.id, second.id)
        assertEquals("https://vimeo.com/12345", first.identity)
        assertNull(first.videoKey)
    }

    @Test
    fun `add rejects a bad url`() = runTest {
        val r = rig()
        expectIllegal { r.queue.add("not a url") }
        assertEquals(emptyList<QueueItem>(), r.queue.items.value)
    }

    // -- happy path ---------------------------------------------------------
    @Test
    fun `success downloads marks done and stores the file`() = runTest {
        val r = rig()
        val item = r.queue.add(URL)
        r.runAll()
        val done = r.queue.item(item.id)!!
        assertEquals("done", done.state)
        assertEquals("Video title", done.title)
        assertEquals("store://Video [$VIDEO_ID].mp4", done.filePath)
        assertEquals(100.0, done.percent!!, 0.0)
        val row = r.row(item)
        assertEquals("done", row.state)
        assertEquals(done.filePath, row.filePath)
        assertNotNull(row.finishedAt)
        assertEquals(done, r.queue.items.value.single())
    }

    @Test
    fun `download request carries the staging dir archive and process id`() = runTest {
        val r = rig()
        r.queue.add(URL)
        r.runAll()
        val request = r.backend.requests.single()
        assertEquals(URL, request.url)
        assertEquals(r.staging, request.stagingDir)
        assertEquals(r.archive.file, request.archiveFile)
        assertEquals("item-1", request.processId)
        assertEquals("bestvideo*+bestaudio/best", request.formatSelector)
        assertEquals(emptyList<String>(), request.extraArgs)
        assertNull(request.limitRate)
        val (staged, name) = r.store.published.single()
        assertEquals(File(r.staging, "Video [$VIDEO_ID].mp4"), staged)
        assertEquals("Video [$VIDEO_ID].mp4", name)
    }

    @Test
    fun `stages go downloading merging converting then done`() = runTest {
        val r = rig()
        r.backend.startHandler = { request, progress ->
            progress(Progress("downloading", status = "downloading", downloadedBytes = 1, totalBytes = 2, percent = 50.0))
            progress(Progress("merging", status = "started", postprocessor = "Merger"))
            progress(Progress("converting", status = "started", postprocessor = "ExtractAudio"))
            FakeHandle().also { it.finish(successOutcome(request)) }
        }
        val events = collect(r.queue)
        val item = r.queue.add(URL)
        r.runAll()
        assertEquals("done", r.queue.item(item.id)!!.state)
        val seen = events.states()
        for (stage in listOf("downloading", "merging", "converting", "done")) assertTrue(stage in seen)
        assertEquals(listOf("probing", "downloading", "merging", "converting", "done"), seen)
        assertTrue(events.any { it is QueueEvent.ProgressChanged })
    }

    @Test
    fun `plain download never shows converting`() = runTest {
        val r = rig()
        r.backend.startHandler = { request, progress ->
            progress(Progress("downloading", status = "downloading", downloadedBytes = 1, totalBytes = 2))
            progress(Progress("downloading", status = "started", postprocessor = "MoveFiles"))
            progress(Progress("downloading", status = "started", postprocessor = "Metadata"))
            FakeHandle().also { it.finish(successOutcome(request)) }
        }
        val events = collect(r.queue)
        r.queue.add(URL)
        r.runAll()
        val seen = events.states()
        assertFalse("converting" in seen)
        assertFalse("merging" in seen)
        assertEquals("done", seen.last())
    }

    // -- failures ------------------------------------------------------------
    @Test
    fun `403 fails with plain language text and no retry`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ ->
            FakeHandle().also { it.finish(failureOutcome("ERROR: unable to download video data: HTTP Error 403: Forbidden")) }
        }
        val item = r.queue.add(URL)
        r.runAll()
        val failed = r.queue.item(item.id)!!
        assertEquals("failed", failed.state)
        assertEquals("http_403", failed.error!!.code)
        assertEquals("The site refused the download.", failed.error!!.message)
        assertEquals(emptyList<Long>(), r.delays.toList())
        assertEquals(1, r.backend.starts)
        assertEquals("http_403", r.row(item).errorCode)
    }

    @Test
    fun `network error backs off 5 15 45 then fails`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ ->
            FakeHandle().also { it.finish(failureOutcome("ERROR: unable to download video data: Connection reset by peer")) }
        }
        val item = r.queue.add(URL)
        val started = testScheduler.currentTime
        r.runAll()
        assertEquals(listOf(5_000L, 15_000L, 45_000L), r.delays.toList())
        assertEquals(BACKOFF_MS, r.delays.toList())
        assertEquals(65_000L, testScheduler.currentTime - started) // virtual time really passed
        val failed = r.queue.item(item.id)!!
        assertEquals("failed", failed.state)
        assertEquals("network", failed.error!!.code)
        assertEquals(4, r.backend.starts) // first try + three retries
    }

    @Test
    fun `network error then success finishes done and clears the error`() = runTest {
        val r = rig()
        val calls = AtomicInteger()
        r.backend.startHandler = { request, _ ->
            FakeHandle().also {
                if (calls.getAndIncrement() == 0) it.finish(failureOutcome("Connection reset")) else it.finish(successOutcome(request))
            }
        }
        val item = r.queue.add(URL)
        r.runAll()
        val done = r.queue.item(item.id)!!
        assertEquals("done", done.state)
        assertNull(done.error)
        assertNull(r.row(item).errorCode)
        assertEquals(listOf(5_000L), r.delays.toList())
    }

    @Test
    fun `non retryable unknown error fails immediately`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("kaboom")) } }
        val item = r.queue.add(URL)
        r.runAll()
        assertEquals("failed", r.queue.item(item.id)!!.state)
        assertEquals("unknown", r.queue.item(item.id)!!.error!!.code)
        assertTrue(r.delays.isEmpty())
        assertEquals(1, r.backend.starts)
    }

    @Test
    fun `probe failure is reported`() = runTest {
        val r = rig()
        r.backend.probeHandler = { throw ProbeFailure("ERROR: Video unavailable") }
        val item = r.queue.add(URL)
        r.runAll()
        val failed = r.queue.item(item.id)!!
        assertEquals("failed", failed.state)
        assertEquals("video_unavailable", failed.error!!.code)
        assertEquals(0, r.backend.starts)
    }

    @Test
    fun `publish failure fails with a plain message`() = runTest {
        val r = rig()
        r.store.failPublish = true
        val item = r.queue.add(URL)
        r.runAll()
        val failed = r.queue.item(item.id)!!
        assertEquals("failed", failed.state)
        assertEquals("publish_failed", failed.error!!.code)
        assertTrue(r.delays.isEmpty())
    }

    // -- pause / resume / cancel / retry ----------------------------------
    @Test
    fun `pause keeps the part file and resume reruns the download`() = runTest {
        val r = rig()
        val handles = CopyOnWriteArrayList<FakeHandle>()
        r.backend.startHandler = { request, progress ->
            progress(Progress("downloading", status = "downloading", downloadedBytes = 5, totalBytes = 10))
            FakeHandle().also {
                handles.add(it)
                if (handles.size == 2) it.finish(successOutcome(request))
            }
        }
        r.staging.mkdirs()
        val part = File(r.staging, "Video [$VIDEO_ID].f137.mp4.part").apply { writeText("half") }
        val item = r.queue.add(URL)
        r.queue.start()
        runCurrent()
        assertEquals("downloading", r.queue.item(item.id)!!.state)

        assertTrue(r.queue.pause(item.id))
        assertEquals("paused", r.queue.item(item.id)!!.state)
        assertTrue(handles[0].cancelled)
        assertTrue(part.exists()) // pause never deletes the .part file
        r.queue.waitUntilIdle()
        assertEquals("paused", r.queue.item(item.id)!!.state)

        assertTrue(r.queue.resume(item.id))
        r.queue.waitUntilIdle()
        assertEquals("done", r.queue.item(item.id)!!.state)
        assertEquals(2, r.backend.starts)
        assertEquals(r.backend.requests[0], r.backend.requests[1]) // same staging dir, so .part continues
        assertTrue(part.exists())
    }

    @Test
    fun `pause of a queued item`() = runTest {
        val r = rig(concurrency = 1)
        val first = r.queue.add(URL)
        val second = r.queue.add("https://youtu.be/zzzzzzzzzzz")
        assertTrue(r.queue.pause(second.id))
        assertEquals("paused", r.queue.item(second.id)!!.state)
        assertTrue(r.queue.pause(first.id)) // still queued, not started
    }

    @Test
    fun `pause while probing keeps the item paused and starts no download`() = runTest {
        val r = rig()
        val gate = CompletableDeferred<Unit>()
        r.backend.probeHandler = {
            gate.await()
            json("""{"id": "x", "title": "T"}""")
        }
        val item = r.queue.add(URL)
        r.queue.start()
        runCurrent()
        assertEquals("probing", r.queue.item(item.id)!!.state)
        assertTrue(r.queue.pause(item.id))
        gate.complete(Unit)
        r.queue.waitUntilIdle()
        assertEquals("paused", r.queue.item(item.id)!!.state)
        assertEquals(0, r.backend.starts)
    }

    @Test
    fun `cancel cancels a running download`() = runTest {
        val r = rig()
        val handle = FakeHandle()
        r.backend.startHandler = { _, _ -> handle }
        val item = r.queue.add(URL)
        r.queue.start()
        runCurrent()
        assertEquals("downloading", r.queue.item(item.id)!!.state)

        assertTrue(r.queue.cancel(item.id))
        assertEquals("cancelled", r.queue.item(item.id)!!.state)
        assertTrue(handle.cancelled)
        r.queue.waitUntilIdle()
        assertEquals("cancelled", r.queue.item(item.id)!!.state)
        assertEquals("cancelled", r.row(item).state)
        assertTrue(r.delays.isEmpty())
    }

    @Test
    fun `cancel a queued item`() = runTest {
        val r = rig()
        val item = r.queue.add(URL)
        assertTrue(r.queue.cancel(item.id))
        assertEquals("cancelled", r.queue.item(item.id)!!.state)
        assertFalse(r.queue.cancel(item.id)) // already terminal
    }

    @Test
    fun `retry after failure clears the error`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("ERROR: Video unavailable")) } }
        val item = r.queue.add(URL)
        r.runAll()
        assertEquals("failed", r.queue.item(item.id)!!.state)

        r.queue.stop() // so the retry is not picked up while we assert
        assertTrue(r.queue.retry(item.id))
        val after = r.queue.item(item.id)!!
        assertEquals("queued", after.state)
        assertNull(after.error)
        assertEquals(0, after.attempts)
        assertNull(r.row(item).errorCode)

        r.runAll()
        assertEquals(2, r.backend.starts)
    }

    @Test
    fun `actions on unknown items return false`() = runTest {
        val r = rig()
        assertFalse(r.queue.pause(999))
        assertFalse(r.queue.resume(999))
        assertFalse(r.queue.retry(999))
        assertFalse(r.queue.cancel(999))
        assertNull(r.queue.item(999))
    }

    // -- concurrency -------------------------------------------------------------
    private fun slowHandler(backend: FakeBackend, active: AtomicInteger, peak: AtomicInteger, ms: (DownloadRequest) -> Long) {
        backend.startHandler = { request, _ ->
            val now = active.incrementAndGet()
            peak.updateAndGet { maxOf(it, now) }
            object : DownloadHandle {
                override suspend fun await(): DownloadOutcome {
                    kotlinx.coroutines.delay(ms(request))
                    active.decrementAndGet()
                    return successOutcome(request, "${request.url.substringAfterLast('/')} [x].mp4")
                }

                override fun cancel() {}
            }
        }
    }

    @Test
    fun `concurrency limit is honoured`() = runTest {
        val r = rig(concurrency = 2)
        val active = AtomicInteger()
        val peak = AtomicInteger()
        slowHandler(r.backend, active, peak) { 50L }
        repeat(6) { r.queue.add("https://vimeo.com/$it") }
        r.runAll()
        assertEquals(2, peak.get())
        assertEquals(setOf("done"), r.queue.items.value.map { it.state }.toSet())
    }

    @Test
    fun `concurrency must be between 1 and 5`() = runTest {
        for (bad in listOf(0, 6, -1)) expectIllegal { rig(concurrency = bad) }
        val r = rig()
        expectIllegal { r.queue.concurrency = 9 }
        expectIllegal { r.queue.concurrency = 0 }
    }

    @Test
    fun `set concurrency is used`() = runTest {
        val r = rig(concurrency = 1)
        r.queue.concurrency = 3
        assertEquals(3, r.queue.concurrency)
        val active = AtomicInteger()
        val peak = AtomicInteger()
        slowHandler(r.backend, active, peak) { 50L }
        repeat(6) { r.queue.add("https://vimeo.com/$it") }
        r.runAll()
        assertEquals(3, peak.get())
    }

    @Test
    fun `fifty adds with concurrency 3 finish every item exactly once`() = runTest {
        val r = rig(concurrency = 3)
        val active = AtomicInteger()
        val peak = AtomicInteger()
        val starts = java.util.concurrent.ConcurrentHashMap<String, AtomicInteger>()
        slowHandler(r.backend, active, peak) { request ->
            starts.computeIfAbsent(request.url) { AtomicInteger() }.incrementAndGet()
            10L + (request.url.hashCode() and 0x1f)
        }
        val events = collect(r.queue)
        val ids = (0 until 50).map { r.queue.add("https://vimeo.com/video$it").id }
        assertEquals(50, ids.toSet().size)
        r.runAll()
        assertTrue(peak.get() in 1..3)
        assertEquals(0, active.get())
        assertEquals(50, starts.size)
        assertTrue(starts.values.all { it.get() == 1 })
        assertEquals(setOf("done"), r.queue.items.value.map { it.state }.toSet())
        val doneEvents = events.filterIsInstance<QueueEvent.StateChanged>().filter { it.state == "done" }
        assertEquals(ids.toSet(), doneEvents.map { it.id }.toSet())
        assertEquals(50, doneEvents.size)
        assertEquals(50, r.history.stateLog.count { it.second == "done" })
    }

    // -- archive -----------------------------------------------------------------
    @Test
    fun `archive skip gives skipped`() = runTest {
        val r = rig()
        r.archive.add("youtube", VIDEO_ID)
        r.store.existing.add("youtube" to VIDEO_ID)
        val item = r.queue.add(URL)
        r.runAll()
        val got = r.queue.item(item.id)!!
        assertEquals("skipped", got.state)
        assertEquals("already_downloaded", got.error!!.code)
        assertEquals("skipped", r.row(item).state)
        assertEquals("already_downloaded", r.row(item).errorCode)
        assertEquals(0, r.backend.starts)
    }

    @Test
    fun `archive entry without a file downloads again`() = runTest {
        val r = rig()
        r.archive.add("youtube", VIDEO_ID)
        val item = r.queue.add(URL)
        r.runAll()
        assertEquals("done", r.queue.item(item.id)!!.state)
        assertEquals(1, r.backend.starts)
        assertFalse(r.archive.has("youtube", VIDEO_ID)) // stale entry was removed
    }

    @Test
    fun `archive is not rewritten while an item downloads`() = runTest {
        val removed = CopyOnWriteArrayList<Pair<String, String>>()
        val spy = object : Archive(File(tmp.root, "data/spy-archive.txt")) {
            override fun remove(extractor: String, videoId: String): Boolean {
                removed.add(extractor to videoId)
                return super.remove(extractor, videoId)
            }
        }
        spy.add("youtube", "STALEID")
        val r = rig(archive = spy)
        val release = CompletableDeferred<Unit>()
        r.backend.startHandler = { request, _ ->
            if (request.url.contains(VIDEO_ID_2)) {
                object : DownloadHandle {
                    override suspend fun await(): DownloadOutcome {
                        release.await()
                        return successOutcome(request, "Video [$VIDEO_ID_2].mp4")
                    }

                    override fun cancel() {}
                }
            } else {
                FakeHandle().also { it.finish(successOutcome(request, "Other [other].mp4")) }
            }
        }
        val busy = r.queue.add(URL_2)
        r.queue.start()
        runCurrent()
        assertEquals("downloading", r.queue.item(busy.id)!!.state)

        val stale = r.queue.add("https://youtu.be/STALEID") // archived, file missing
        runCurrent() // advanceUntilIdle skips backgroundScope work
        assertEquals("done", r.queue.item(stale.id)!!.state) // read-only reconcile -> downloads
        assertEquals("downloading", r.queue.item(busy.id)!!.state) // busy item still running
        assertEquals(emptyList<Pair<String, String>>(), removed.toList()) // never rewritten while busy
        assertTrue(spy.has("youtube", "STALEID"))

        release.complete(Unit)
        r.queue.waitUntilIdle()
        assertEquals("done", r.queue.item(busy.id)!!.state)
        assertTrue(spy.has("youtube", "STALEID"))

        // Now the queue is idle: the stale entry is removed as usual.
        spy.add("youtube", "STALEID2")
        val third = r.queue.add("https://youtu.be/STALEID2")
        r.queue.waitUntilIdle()
        assertEquals("done", r.queue.item(third.id)!!.state)
        assertEquals(listOf("youtube" to "STALEID2"), removed.toList())
        assertFalse(spy.has("youtube", "STALEID2"))
    }

    @Test
    fun `archive calls are serialised across real threads`() {
        class OverlapArchive(file: File) : Archive(file) {
            private val busy = java.util.concurrent.locks.ReentrantLock()
            val overlaps = AtomicInteger()

            private fun <T> guarded(block: () -> T): T {
                if (!busy.tryLock()) {
                    overlaps.incrementAndGet()
                    busy.lock()
                }
                try {
                    Thread.sleep(2)
                    return block()
                } finally {
                    busy.unlock()
                }
            }

            override fun has(extractor: String, videoId: String) = guarded { super.has(extractor, videoId) }
            override fun remove(extractor: String, videoId: String) = guarded { super.remove(extractor, videoId) }
        }

        val shared = OverlapArchive(File(tmp.root, "data/shared-archive.txt"))
        val scope = CoroutineScope(Dispatchers.Default)
        try {
            runBlocking {
                withTimeout(30_000) {
                    val r = Rig(scope, tmp.root, concurrency = 4, archive = shared)
                    for (i in 0 until 4) r.queue.add("https://youtu.be/id$i")
                    r.runAll()
                    assertEquals(setOf("done"), r.queue.items.value.map { it.state }.toSet())
                }
            }
        } finally {
            scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
        }
        assertEquals(0, shared.overlaps.get())
    }

    // -- events and snapshots --------------------------------------------------------
    @Test
    fun `events reach every collector`() = runTest {
        val r = rig()
        val one = collect(r.queue)
        val two = collect(r.queue)
        r.queue.add(URL)
        r.runAll()
        assertTrue(one.any { it is QueueEvent.Added })
        assertTrue(one.any { it is QueueEvent.StateChanged })
        assertTrue(one.any { it is QueueEvent.ItemUpdated }) // title arrived
        assertEquals(one.toList(), two.toList())
    }

    @Test
    fun `items state flow follows the queue`() = runTest {
        val r = rig()
        assertEquals(emptyList<QueueItem>(), r.queue.items.value)
        val added = r.queue.add(URL)
        assertEquals(listOf(added), r.queue.items.value)
        r.runAll()
        assertEquals("done", r.queue.items.value.single().state)
    }

    @Test
    fun `stop pauses running items`() = runTest {
        val r = rig()
        val handle = FakeHandle()
        r.backend.startHandler = { _, _ -> handle }
        val item = r.queue.add(URL)
        r.queue.start()
        runCurrent()
        assertEquals("downloading", r.queue.item(item.id)!!.state)
        r.queue.stop()
        assertEquals("paused", r.queue.item(item.id)!!.state)
        assertTrue(handle.cancelled)
        r.queue.waitUntilIdle()
        assertEquals("paused", r.queue.item(item.id)!!.state)
    }

    // -- brief 1D ports ---------------------------------------------------------------
    @Test
    fun `reported file path becomes the item file path`() = runTest {
        val r = rig()
        r.backend.startHandler = { request, _ ->
            FakeHandle().also { it.finish(successOutcome(request, "Weird name.mp4")) }
        }
        val item = r.queue.add("https://example.com/clip.mp4")
        r.runAll()
        val done = r.queue.item(item.id)!!
        assertEquals("done", done.state)
        assertEquals("store://Weird name.mp4", done.filePath)
        assertEquals(done.filePath, r.row(item).filePath)
    }

    @Test
    fun `silent archive skip is reported as skipped`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ ->
            FakeHandle().also {
                it.finish(DownloadOutcome(0, "[generic] clip: has already been recorded in the archive", null, alreadyArchived = true))
            }
        }
        val item = r.queue.add("https://example.com/clip.mp4")
        r.runAll()
        val got = r.queue.item(item.id)!!
        assertEquals("skipped", got.state)
        assertEquals("already_downloaded", got.error!!.code)
        assertEquals("skipped", r.row(item).state)
    }

    @Test
    fun `archive skip text with a new file is still done`() = runTest {
        val r = rig()
        r.backend.startHandler = { request, _ ->
            FakeHandle().also { it.finish(successOutcome(request, "clip.mp4").copy(alreadyArchived = true)) }
        }
        val item = r.queue.add("https://example.com/clip.mp4")
        r.runAll()
        assertEquals("done", r.queue.item(item.id)!!.state)
    }

    @Test
    fun `done without a reported file stays done with no path`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(DownloadOutcome(0, "", null)) } }
        val item = r.queue.add("https://example.com/clip.mp4")
        r.runAll()
        val done = r.queue.item(item.id)!!
        assertEquals("done", done.state)
        assertNull(done.filePath)
        assertTrue(r.store.published.isEmpty())
    }

    // -- re-adding ----------------------------------------------------------------------
    @Test
    fun `readding a done item with its file changes nothing`() = runTest {
        val r = rig()
        val first = r.queue.add(URL)
        r.runAll()
        assertEquals("done", r.queue.item(first.id)!!.state)
        val again = r.queue.add(URL)
        assertEquals(first.id, again.id)
        assertEquals("done", again.state)
        assertEquals(1, r.backend.starts)
    }

    @Test
    fun `readding a done item after deleting its file downloads again`() = runTest {
        val r = rig()
        val first = r.queue.add(URL)
        r.runAll()
        val done = r.queue.item(first.id)!!
        assertEquals("done", done.state)
        r.archive.add("youtube", VIDEO_ID)
        r.store.deleteEverything()

        val again = r.queue.add(URL)
        assertEquals(first.id, again.id)
        assertEquals("queued", again.state)
        assertNull(again.error)
        assertNull(again.filePath)
        assertFalse(r.archive.has("youtube", VIDEO_ID))
        assertEquals("queued", r.row(first).state)
        assertTrue(("youtube" to VIDEO_ID) in r.store.forgotten)

        r.queue.waitUntilIdle()
        assertEquals("done", r.queue.item(first.id)!!.state)
        assertEquals(2, r.backend.starts)
    }

    @Test
    fun `readding a skipped item with a missing file downloads again`() = runTest {
        val r = rig()
        r.archive.add("youtube", VIDEO_ID)
        r.store.existing.add("youtube" to VIDEO_ID)
        val first = r.queue.add(URL)
        r.runAll()
        assertEquals("skipped", r.queue.item(first.id)!!.state)
        assertEquals("skipped", r.queue.add(URL).state) // file still there

        r.store.existing.clear()
        assertEquals("queued", r.queue.add(URL).state)
        r.queue.waitUntilIdle()
        assertEquals("done", r.queue.item(first.id)!!.state)
    }

    @Test
    fun `readding a failed item queues it again`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("HTTP Error 403: Forbidden")) } }
        val first = r.queue.add(URL)
        r.runAll()
        assertEquals("failed", r.queue.item(first.id)!!.state)
        val again = r.queue.add(URL)
        assertEquals(first.id, again.id) // same item, not a second one
        assertEquals("queued", again.state)
        assertNull(again.error)
        assertEquals(0, again.attempts)
    }

    @Test
    fun `non youtube archive key comes from the probe`() = runTest {
        val r = rig()
        r.backend.probeHandler = { json("""{"id": "clip", "title": "t", "extractor_key": "Generic"}""") }
        r.archive.add("generic", "clip") // stale: no file in the output location
        val item = r.queue.add("https://example.com/clip.mp4")
        r.runAll()
        assertEquals("done", r.queue.item(item.id)!!.state)
        assertFalse(r.archive.has("generic", "clip"))
    }

    // -- runtime setters ------------------------------------------------------------------
    @Test
    fun `setters apply to the next started download`() = runTest {
        val r = rig()
        r.backend.probeHandler = { json("""{"title": "T"}""") }
        r.queue.setLimitRate("2M")
        r.queue.setFormatSelector("wv*+wa/w")
        r.queue.setExtraArgs(listOf("-x", "--audio-format", "mp3"))
        r.queue.add("https://vimeo.com/1")
        r.runAll()
        val first = r.backend.requests[0]
        assertEquals("2M", first.limitRate)
        assertEquals("wv*+wa/w", first.formatSelector)
        assertEquals(listOf("-x", "--audio-format", "mp3"), first.extraArgs)

        r.queue.setLimitRate(null)
        r.queue.setExtraArgs(emptyList())
        r.queue.add("https://vimeo.com/2")
        r.queue.waitUntilIdle()
        assertNull(r.backend.requests[1].limitRate)
        assertEquals(emptyList<String>(), r.backend.requests[1].extraArgs)
    }

    @Test
    fun `set format selector rejects empty`() = runTest {
        expectIllegal { rig().queue.setFormatSelector("") }
    }

    // -- per item overrides ------------------------------------------------------------------
    @Test
    fun `item overrides beat queue defaults`() = runTest {
        val r = rig()
        r.queue.setFormatSelector("best")
        r.queue.setExtraArgs(listOf("-x"))
        r.queue.add("https://vimeo.com/1", formatSelector = "137+140", extraArgs = listOf("--remux-video", "mp4"), title = "Shown first")
        r.queue.add("https://vimeo.com/2") // no overrides: queue defaults
        r.runAll()
        val byUrl = r.backend.requests.associateBy { it.url }
        assertEquals("137+140", byUrl.getValue("https://vimeo.com/1").formatSelector)
        assertEquals(listOf("--remux-video", "mp4"), byUrl.getValue("https://vimeo.com/1").extraArgs)
        assertEquals("best", byUrl.getValue("https://vimeo.com/2").formatSelector)
        assertEquals(listOf("-x"), byUrl.getValue("https://vimeo.com/2").extraArgs)
    }

    @Test
    fun `empty extra args override still wins`() = runTest {
        val r = rig()
        r.queue.setExtraArgs(listOf("-x", "--audio-format", "mp3"))
        r.queue.add("https://vimeo.com/1", formatSelector = "22", extraArgs = emptyList())
        r.runAll()
        assertEquals(emptyList<String>(), r.backend.requests.single().extraArgs)
    }

    @Test
    fun `title override is shown before the probe`() = runTest {
        val r = rig()
        assertEquals("Chosen title", r.queue.add("https://vimeo.com/1", title = "  Chosen title ").title)
    }

    @Test
    fun `probe title replaces the override`() = runTest {
        val r = rig()
        r.backend.probeHandler = { json("""{"title": "Probed"}""") }
        val item = r.queue.add("https://vimeo.com/1", title = "Shown first")
        r.runAll()
        assertEquals("Probed", r.queue.item(item.id)!!.title)
    }

    @Test
    fun `duplicate add keeps original overrides`() = runTest {
        val r = rig()
        val first = r.queue.add("https://vimeo.com/1", formatSelector = "137+140")
        val again = r.queue.add("https://vimeo.com/1", formatSelector = "18", extraArgs = listOf("-x"))
        assertEquals(first, again)
        r.runAll()
        assertEquals(1, r.backend.starts)
        assertEquals("137+140", r.backend.requests.single().formatSelector)
        assertEquals(emptyList<String>(), r.backend.requests.single().extraArgs)
    }
}
