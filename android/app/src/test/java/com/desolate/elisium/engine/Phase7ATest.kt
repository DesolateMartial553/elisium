package com.desolate.elisium.engine

import com.desolate.elisium.service.NetworkGate
import com.desolate.elisium.service.shareConfirmation
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val ID = "dQw4w9WgXcQ"
private const val LINK = "https://www.youtube.com/watch?v=$ID"
private val TERMINATED = DownloadOutcome(exitCode = -1, rawLog = "", filePath = null, terminated = true)

/** A handle whose process "dies" only when the test says so: cancel() does not complete [result]. */
private class SlowHandle : DownloadHandle {
    val result = CompletableDeferred<DownloadOutcome>()

    @Volatile
    var cancelled = false

    override suspend fun await(): DownloadOutcome = result.await()
    override fun cancel() {
        cancelled = true
    }
}

/** Store whose publish blocks until [gate] opens, and records deletes. */
private class GatedStore : OutputStore {
    val gate = CompletableDeferred<Unit>()
    val publishCalls = CopyOnWriteArrayList<String>()
    val deleted = CopyOnWriteArrayList<String>()
    override fun existsFor(extractorKey: String, videoId: String) = false
    override suspend fun publish(stagedFile: File, displayName: String): PublishedFile {
        publishCalls.add(displayName)
        gate.await()
        return PublishedFile("store://$displayName", displayName)
    }

    override fun delete(location: String): Boolean {
        deleted.add(location)
        return true
    }

    override fun forget(extractorKey: String, videoId: String) = Unit
}

private class ThrowingHistory : HistoryStore {
    override fun add(url: String, videoKey: String?, title: String?, state: String, errorCode: String?, errorMessage: String?, filePath: String?): Long =
        throw IllegalStateException("database or disk is full")

    override fun updateState(recordId: Long, state: String, errorCode: String?, errorMessage: String?, filePath: String?, clearError: Boolean): Boolean =
        throw IllegalStateException("database or disk is full")

    override fun get(recordId: Long): HistoryRecord? = null
    override fun search(text: String, limit: Int?): List<HistoryRecord> = emptyList()
    override fun recent(limit: Int): List<HistoryRecord> = throw IllegalStateException("database or disk is full")
    override fun delete(recordId: Long) = false
}

@OptIn(ExperimentalCoroutinesApi::class)
class Phase7ATest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val backend = FakeBackend()
    private val history = FakeHistory()
    private lateinit var store: OutputStore

    private fun TestScope.queue(
        outputStore: OutputStore = FakeStore(),
        hist: HistoryStore = history,
    ): DownloadQueue {
        store = outputStore
        return DownloadQueue(
            hist, Archive(File(tmp.root, "data/archive.txt")), outputStore, backend, File(tmp.root, "staging"), backgroundScope,
        )
    }

    private val staging get() = File(tmp.root, "staging")

    /** First start gives a slow handle (kept in [handles]); later starts succeed at once. */
    private fun slowFirst(handles: MutableList<SlowHandle>) {
        backend.startHandler = { request, _ ->
            if (handles.isEmpty()) {
                SlowHandle().also { handles.add(it) }
            } else {
                FakeHandle().also { it.finish(successOutcome(request)) }
            }
        }
    }

    // -- finding 4: pause then quick resume ----------------------------------------
    @Test
    fun `pause then quick resume restarts instead of failing`() = runTest {
        val q = queue()
        val handles = CopyOnWriteArrayList<SlowHandle>()
        slowFirst(handles)
        val item = q.add(LINK)
        q.start()
        runCurrent()
        assertEquals("downloading", q.item(item.id)!!.state)

        assertTrue(q.pause(item.id))
        assertTrue(q.resume(item.id)) // before the old worker woke up
        assertEquals("queued", q.item(item.id)!!.state)
        handles[0].result.complete(TERMINATED) // the old process finally dies

        q.waitUntilIdle()
        val done = q.item(item.id)!!
        assertEquals("done", done.state)
        assertNull(done.error)
        assertEquals(2, backend.starts)
    }

    @Test
    fun `late progress from the old process is ignored`() = runTest {
        val q = queue()
        val handles = CopyOnWriteArrayList<SlowHandle>()
        val callbacks = CopyOnWriteArrayList<(Progress) -> Unit>()
        backend.startHandler = { _, progress ->
            callbacks.add(progress)
            SlowHandle().also { handles.add(it) }
        }
        val item = q.add(LINK)
        q.start()
        runCurrent()
        q.pause(item.id)
        q.resume(item.id)
        callbacks[0](Progress("downloading", percent = 50.0)) // dying process, item is queued again
        assertEquals("queued", q.item(item.id)!!.state)
        assertNull(q.item(item.id)!!.percent)

        handles[0].result.complete(TERMINATED)
        runCurrent()
        assertEquals("downloading", q.item(item.id)!!.state) // second attempt is running
        callbacks[0](Progress("downloading", percent = 77.0)) // stale token
        assertNull(q.item(item.id)!!.percent)
        callbacks[1](Progress("downloading", percent = 10.0))
        assertEquals(10.0, q.item(item.id)!!.percent!!, 0.001)

        handles[1].result.complete(successOutcome(backend.requests[1]))
        q.waitUntilIdle()
        assertEquals("done", q.item(item.id)!!.state)
    }

    @Test
    fun `wifi hold flapping resumes the download instead of failing it`() = runTest {
        val q = queue()
        val gate = NetworkGate(q)
        val handles = CopyOnWriteArrayList<SlowHandle>()
        slowFirst(handles)
        gate.setAllowed(true)
        val item = q.add(LINK)
        runCurrent()
        assertEquals("downloading", q.item(item.id)!!.state)

        gate.setAllowed(false) // left Wi-Fi
        assertEquals("paused", q.item(item.id)!!.state)
        gate.setAllowed(true) // back on Wi-Fi within a second
        assertEquals("queued", q.item(item.id)!!.state)
        handles[0].result.complete(TERMINATED)

        q.waitUntilIdle()
        assertEquals("done", q.item(item.id)!!.state)
        assertEquals(2, backend.starts)
    }

    @Test
    fun `terminated outcome in a running state is still a failure`() = runTest {
        val q = queue()
        backend.startHandler = { _, _ -> FakeHandle().also { it.finish(TERMINATED.copy(rawLog = "killed")) } }
        val item = q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertEquals("failed", q.item(item.id)!!.state) // never stuck in "downloading"
    }

    // -- finding 10: cancel during publish -------------------------------------------
    @Test
    fun `cancel during the copy deletes the published file`() = runTest {
        val gated = GatedStore()
        val q = queue(gated)
        val item = q.add(LINK)
        q.start()
        runCurrent()
        assertEquals(1, gated.publishCalls.size) // worker is inside publish
        assertTrue(q.cancel(item.id))
        gated.gate.complete(Unit)
        q.waitUntilIdle()
        assertEquals("cancelled", q.item(item.id)!!.state)
        assertEquals(1, gated.deleted.size)
        assertNull(history.get(item.recordId)!!.filePath)
    }

    @Test
    fun `finished file of a cancelled item is not published and the staged file is deleted`() = runTest {
        val fake = FakeStore()
        val q = queue(fake)
        val handle = SlowHandle()
        backend.startHandler = { _, _ -> handle }
        val item = q.add(LINK)
        q.start()
        runCurrent()
        staging.mkdirs()
        val staged = File(staging, "Video [$ID].mp4").apply { writeText("data") }
        q.cancel(item.id)
        handle.result.complete(DownloadOutcome(0, "", staged.path)) // finished just as the cancel landed
        q.waitUntilIdle()
        assertTrue(fake.published.isEmpty())
        assertFalse(staged.exists())
        assertEquals("cancelled", q.item(item.id)!!.state)
    }

    @Test
    fun `pause during the copy still ends done because the file is saved`() = runTest {
        val gated = GatedStore()
        val q = queue(gated)
        val item = q.add(LINK)
        q.start()
        runCurrent()
        q.pause(item.id)
        gated.gate.complete(Unit)
        q.waitUntilIdle()
        val got = q.item(item.id)!!
        assertEquals("done", got.state)
        assertEquals("store://Video [$ID].mp4", got.filePath)
        assertTrue(gated.deleted.isEmpty())
    }

    // -- finding 12: re-adding ---------------------------------------------------
    @Test
    fun `readding a cancelled link queues it again and the message says so`() = runTest {
        val q = queue()
        val item = q.add(LINK)
        q.cancel(item.id)
        assertEquals("cancelled", q.item(item.id)!!.state)
        val line = queueLinks(q, listOf(LINK))
        assertEquals("queued", q.item(item.id)!!.state)
        assertEquals("1 link queued again", line)
    }

    @Test
    fun `readding a queued or running link is still just already in the list`() = runTest {
        val q = queue()
        q.add(LINK)
        assertEquals("Added 0 links (1 already in the list)", queueLinks(q, listOf(LINK)))
        assertEquals("Added 1 link", queueLinks(q, listOf("https://vimeo.com/1")))
    }

    @Test
    fun `confirmation line with retried links`() {
        assertEquals("1 link queued again", shareConfirmation(0, 0, 1, retried = 1))
        assertEquals("2 links queued again (1 already in the list)", shareConfirmation(0, 1, 3, retried = 2))
        assertEquals("Added 1 link, 1 queued again", shareConfirmation(1, 0, 2, retried = 1))
        assertEquals("Added 1 link", shareConfirmation(1, 0, 1))
    }

    // -- finding 13: history errors ---------------------------------------------
    @Test
    fun `a failing history store does not stop a download`() = runTest {
        val q = queue(hist = ThrowingHistory())
        val item = q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertEquals("done", q.item(item.id)!!.state)
    }

    // -- finding 14: storage permission -----------------------------------------
    @Test
    fun `missing storage permission is reported as such not as free space`() = runTest {
        val denied = object : OutputStore {
            override fun existsFor(extractorKey: String, videoId: String) = false
            override suspend fun publish(stagedFile: File, displayName: String): PublishedFile? = throw StoragePermissionException()
            override fun forget(extractorKey: String, videoId: String) = Unit
        }
        val q = queue(denied)
        val item = q.add(LINK)
        q.start()
        q.waitUntilIdle()
        val got = q.item(item.id)!!
        assertEquals("failed", got.state)
        assertEquals("storage_permission", got.error!!.code)
        assertTrue("storage" in got.error!!.message.lowercase())
    }

    // -- finding 7: staging cleanup ------------------------------------------------
    private fun stage(vararg names: String): List<File> {
        File(staging, "tmp").mkdirs()
        return names.map { name ->
            val dir = if (name.endsWith(".part")) File(staging, "tmp") else staging
            File(dir, name).apply { writeText("x") }
        }
    }

    @Test
    fun `cancel deletes the item files including part files`() = runTest {
        val q = queue()
        backend.startHandler = { _, _ -> FakeHandle() } // cancel() completes it
        val item = q.add(LINK)
        q.start()
        runCurrent()
        val files = stage("Video [$ID].f137.mp4.part", "Video [$ID].mp4", "item-${item.id}.path")
        val other = stage("Other [zzzzzzzzzzz].mp4.part").single()
        q.cancel(item.id)
        q.waitUntilIdle()
        files.forEach { assertFalse("${it.name} should be gone", it.exists()) }
        assertTrue(other.exists()) // another item's files are untouched
    }

    @Test
    fun `cancel of a paused item deletes its part files`() = runTest {
        val q = queue()
        val item = q.add(LINK)
        q.pause(item.id)
        val part = stage("Video [$ID].f137.mp4.part").single()
        assertTrue(q.cancel(item.id))
        assertFalse(part.exists())
    }

    @Test
    fun `a non retryable failure deletes the leftovers`() = runTest {
        val q = queue()
        backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("ERROR: HTTP Error 403: Forbidden")) } }
        val item = q.add(LINK)
        val files = stage("Video [$ID].f137.mp4.part", "Video [$ID].f140.m4a")
        q.start()
        q.waitUntilIdle()
        assertEquals("failed", q.item(item.id)!!.state)
        files.forEach { assertFalse(it.exists()) }
    }

    @Test
    fun `a network failure keeps part files for the retry but deletes finished leftovers`() = runTest {
        val q = queue()
        backend.startHandler = { _, _ -> FakeHandle().also { it.finish(failureOutcome("ERROR: unable to download: Connection reset")) } }
        val item = q.add(LINK)
        val (part, whole) = stage("Video [$ID].f137.mp4.part", "Video [$ID].f140.m4a")
        q.start()
        q.waitUntilIdle()
        assertEquals("failed", q.item(item.id)!!.state)
        assertTrue(part.exists())
        assertFalse(whole.exists())
    }

    @Test
    fun `a publish failure deletes the staged file`() = runTest {
        val fake = FakeStore().also { it.failPublish = true }
        val q = queue(fake)
        val staged = stage("Video [$ID].mp4").single()
        backend.startHandler = { _, _ -> FakeHandle().also { it.finish(DownloadOutcome(0, "", staged.path)) } }
        val item = q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertEquals("publish_failed", q.item(item.id)!!.error!!.code)
        assertFalse(staged.exists())
    }

    @Test
    fun `an archived skip deletes leftovers`() = runTest {
        val fake = FakeStore()
        val q = queue(fake)
        Archive(File(tmp.root, "data/archive.txt")).add("youtube", ID)
        fake.existing.add("youtube" to ID)
        val leftover = stage("Video [$ID].mp4").single()
        val item = q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertEquals("skipped", q.item(item.id)!!.state)
        assertFalse(leftover.exists())
    }

    @Test
    fun `item leftovers helper keeps part files only when asked`() {
        val dir = tmp.newFolder("st")
        File(dir, "tmp").mkdirs()
        val part = File(dir, "tmp/A [x1].mp4.part").apply { writeText("p") }
        val ytdl = File(dir, "tmp/A [x1].mp4.ytdl").apply { writeText("p") }
        val frag = File(dir, "tmp/A [x1].mp4.part-Frag3").apply { writeText("p") }
        val whole = File(dir, "A [x1].mp4").apply { writeText("w") }
        val path = File(dir, "item-9.path").apply { writeText("p") }
        assertEquals(2, deleteItemLeftovers(dir, "item-9", "x1", keepPartial = true))
        assertTrue(part.exists() && ytdl.exists() && frag.exists())
        assertFalse(whole.exists() || path.exists())
        assertEquals(3, deleteItemLeftovers(dir, "item-9", "x1", keepPartial = false))
        assertFalse(part.exists() || ytdl.exists() || frag.exists())
    }

    @Test
    fun `leftovers helper never matches by name without a video id`() {
        val dir = tmp.newFolder("st2")
        val file = File(dir, "A [x1].mp4").apply { writeText("w") }
        assertEquals(0, deleteItemLeftovers(dir, "item-1", null, keepPartial = false))
        assertEquals(0, deleteItemLeftovers(dir, "item-1", "", keepPartial = false))
        assertTrue(file.exists())
    }

    @Test
    fun `orphan sweep removes only files older than the limit`() {
        val dir = tmp.newFolder("st3")
        File(dir, "tmp").mkdirs()
        val now = 10L * ORPHAN_MAX_AGE_MS
        val old = File(dir, "old.mp4").apply { writeText("o"); setLastModified(now - ORPHAN_MAX_AGE_MS - 1000) }
        val oldPart = File(dir, "tmp/old.part").apply { writeText("o"); setLastModified(now - ORPHAN_MAX_AGE_MS - 1000) }
        val fresh = File(dir, "fresh.mp4").apply { writeText("f"); setLastModified(now - 1000) }
        assertEquals(2, sweepOrphans(dir, ORPHAN_MAX_AGE_MS, now))
        assertFalse(old.exists() || oldPart.exists())
        assertTrue(fresh.exists())
        assertEquals(0, sweepOrphans(File(dir, "missing"), ORPHAN_MAX_AGE_MS, now))
    }

    // -- finding 6: process kill recovery ---------------------------------------
    @Test
    fun `interrupted rows are marked failed at startup and finished rows are left alone`() {
        val h = FakeHistory()
        val states = listOf("queued", "probing", "downloading", "merging", "converting", "paused", "done", "failed", "skipped", "cancelled")
        val ids = states.associateWith { h.add("https://example.com/$it", state = it) }
        assertEquals(6, recoverInterrupted(h))
        for (s in listOf("queued", "probing", "downloading", "merging", "converting", "paused")) {
            val row = h.get(ids.getValue(s))!!
            assertEquals("failed", row.state)
            assertEquals("interrupted", row.errorCode)
            assertEquals("Interrupted when the app closed. Tap Retry.", row.errorMessage)
        }
        for (s in listOf("done", "failed", "skipped", "cancelled")) assertEquals(s, h.get(ids.getValue(s))!!.state)
        assertEquals(0, recoverInterrupted(h)) // idempotent
    }

    @Test
    fun `recovery survives a database error`() {
        assertEquals(0, recoverInterrupted(ThrowingHistory()))
    }

    // -- finding 8: expected size reaches the request -----------------------------
    @Test
    fun `probe filesize becomes the expected bytes of the request`() = runTest {
        val q = queue()
        backend.probeHandler = { json("""{"id": "x", "title": "T", "filesize": 3000000000}""") }
        q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertEquals(3_000_000_000L, backend.requests.single().expectedBytes)
    }

    @Test
    fun `no size in the probe means unknown`() = runTest {
        val q = queue()
        q.add(LINK)
        q.start()
        q.waitUntilIdle()
        assertNull(backend.requests.single().expectedBytes)
    }
}
