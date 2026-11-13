package com.desolate.elisium.engine

import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/**
 * JVM stand-in for `test_e2e_local.py`: the same user-visible flow, but with a fake
 * backend that writes a real staged file and appends to the real archive file (as
 * yt-dlp would) and a directory-backed OutputStore. No yt-dlp, ffmpeg or network.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class QueueLocalFlowTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val link = "http://127.0.0.1:8000/clip.mp4"

    private inner class Env(scope: TestScope) {
        val out = File(tmp.root, "out")
        val staging = File(tmp.root, "cache/tmp")
        val archive = Archive(File(tmp.root, "archive.txt"))
        val history = FakeHistory()
        val store = FakeStore(out)
        val backend = FakeBackend().apply {
            probeHandler = { json("""{"id": "clip", "title": "clip", "extractor_key": "Generic"}""") }
            startHandler = { request, _ ->
                request.stagingDir.mkdirs()
                val staged = File(request.stagingDir, "clip [clip].mp4").apply { writeText("video") }
                // yt-dlp itself appends to the shared archive file.
                request.archiveFile.let { Archive(it).add("generic", "clip") }
                FakeHandle().also { it.finish(DownloadOutcome(0, "", staged.path)) }
            }
        }
        val scope = scope.backgroundScope

        fun newQueue(): DownloadQueue =
            DownloadQueue(history, archive, store, backend, staging, scope).also { it.start() }

        fun finished(): List<File> = out.listFiles()?.sortedBy { it.name } ?: emptyList()
    }

    private suspend fun runOne(q: DownloadQueue, url: String): QueueItem {
        val item = q.add(url)
        q.waitUntilIdle()
        return q.item(item.id)!!
    }

    @Test
    fun `local download end to end`() = runTest {
        val env = Env(this)
        val q = env.newQueue()
        val ids = setOf(q.add(link).id, q.add(link).id, q.add("$link?utm_source=x").id)
        assertEquals(1, ids.size)
        q.waitUntilIdle()

        val item = q.items.value.single()
        assertEquals(item.toString(), "done", item.state)
        assertNotNull(item.filePath)
        assertTrue(File(item.filePath!!).isFile)
        assertEquals(env.out, File(item.filePath!!).parentFile)
        assertEquals(1, env.finished().size)
        assertTrue(env.out.list()!!.none { it.endsWith(".part") })
        assertTrue(env.staging.list()!!.isEmpty()) // publish moved the staged file
        assertTrue(env.archive.has("generic", "clip"))
        assertEquals(item.filePath, env.history.get(item.recordId)!!.filePath)

        // Fresh queue, same URL: archived and the file is there -> skipped.
        val q2 = env.newQueue()
        val again = runOne(q2, link)
        assertEquals(again.toString(), "skipped", again.state)
        assertEquals(1, env.finished().size)
        assertEquals(1, env.backend.starts)
    }

    @Test
    fun `redownload after deleting the file`() = runTest {
        val env = Env(this)
        val q = env.newQueue()
        val first = runOne(q, link)
        assertEquals("done", first.state)
        File(first.filePath!!).delete()

        // Same queue: add() notices the missing file and queues it again.
        assertEquals("queued", q.add(link).state)
        q.waitUntilIdle()
        val second = q.item(first.id)!!
        assertEquals(second.toString(), "done", second.state)
        assertTrue(File(second.filePath!!).isFile)
        assertEquals(1, env.finished().size)

        // Fresh queue: the archive is reconciled from the probe's id.
        File(second.filePath!!).delete()
        val q2 = env.newQueue()
        val third = runOne(q2, link)
        assertEquals(third.toString(), "done", third.state)
        assertTrue(File(third.filePath!!).isFile)
        assertEquals(1, env.finished().size)
        assertEquals(3, env.backend.starts)
        assertFalse(env.finished().isEmpty())
    }
}
