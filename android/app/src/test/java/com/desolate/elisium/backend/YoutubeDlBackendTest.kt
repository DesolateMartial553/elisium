package com.desolate.elisium.backend

import com.desolate.elisium.engine.DownloadRequest
import com.desolate.elisium.engine.ProbeFailure
import com.desolate.elisium.engine.Progress
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** Scripted runner: [script] sees the call and may write the path file, emit lines, block, and return a result. */
private class FakeRunner(
    var script: (calls: Call, onLine: (String) -> Unit) -> RunResult = { _, _ -> RunResult(0, "{}", "") },
) : YtDlpRunner {
    data class Call(val args: List<String>, val url: String, val processId: String)

    val calls = CopyOnWriteArrayList<Call>()
    val destroyed = CopyOnWriteArrayList<String>()
    val destroyLatch = CountDownLatch(1)

    override fun run(args: List<String>, url: String, processId: String, onLine: (String) -> Unit): RunResult {
        val call = Call(args, url, processId)
        calls.add(call)
        return script(call, onLine)
    }

    override fun destroy(processId: String): Boolean {
        destroyed.add(processId)
        destroyLatch.countDown()
        return true
    }
}

private val GB = 1024L * 1024 * 1024

class YoutubeDlBackendTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val scope = CoroutineScope(Dispatchers.IO)

    private fun request(staging: File, id: String = "item-1") = DownloadRequest(
        url = "https://youtu.be/dQw4w9WgXcQ",
        formatSelector = "best",
        extraArgs = emptyList(),
        limitRate = null,
        archiveFile = File(staging.parentFile, "archive.txt"),
        stagingDir = staging,
        processId = id,
    )

    private fun backend(runner: FakeRunner, free: Long = GB) = YoutubeDlBackend(runner, scope) { free }

    // -- probe -----------------------------------------------------------
    @Test
    fun probeParsesTheJsonAndUsesTheProbeArgs() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(0, """{"id": "abc", "title": "Hello"}""", "") }
        val info = backend(runner).probe("https://youtu.be/abc")
        assertEquals("Hello", info["title"]!!.jsonPrimitive.content)
        assertEquals(listOf("-J", "--no-download", "--no-playlist"), runner.calls.single().args)
        assertEquals("https://youtu.be/abc", runner.calls.single().url)
        assertTrue(runner.calls.single().processId.startsWith("probe-"))
    }

    @Test
    fun probeUsesFlatPlaylistForAPlaylistLink() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(0, "{}", "") }
        backend(runner).probe("https://www.youtube.com/playlist?list=PL1")
        assertTrue("--flat-playlist" in runner.calls.single().args)
    }

    @Test
    fun probeToleratesNoiseAroundTheJson() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(0, "WARNING: x\n{\"id\": \"a\"}\ntrailing", "") }
        assertEquals("a", backend(runner).probe("https://x.com/v")["id"]!!.jsonPrimitive.content)
    }

    @Test
    fun probeFailureCarriesTheRawText() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(1, "", "ERROR: Video unavailable") }
        try {
            backend(runner).probe("https://x.com/v")
            fail("expected ProbeFailure")
        } catch (f: ProbeFailure) {
            assertTrue("Video unavailable" in f.raw)
        }
    }

    @Test
    fun probeWithUnparsableOutputFails() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(0, "not json at all", "warn") }
        try {
            backend(runner).probe("https://x.com/v")
            fail("expected ProbeFailure")
        } catch (f: ProbeFailure) {
            assertTrue("not json at all" in f.raw)
        }
    }

    @Test
    fun cancellingAProbeDestroysTheProcess() = runBlocking {
        val release = CountDownLatch(1)
        val started = CountDownLatch(1)
        val runner = FakeRunner { _, _ ->
            started.countDown()
            release.await(5, TimeUnit.SECONDS)
            RunResult(-1, "", "", canceled = true)
        }
        val job = async(Dispatchers.Default) { backend(runner).probe("https://x.com/v") }
        assertTrue(started.await(5, TimeUnit.SECONDS))
        job.cancel()
        assertTrue("process was not destroyed", runner.destroyLatch.await(5, TimeUnit.SECONDS))
        assertTrue(runner.destroyed.single().startsWith("probe-"))
        release.countDown()
        job.cancelAndJoin()
    }

    // -- extractJsonObject -----------------------------------------------
    @Test
    fun extractJsonObjectCases() {
        assertNotNull(extractJsonObject("""{"a": 1}"""))
        assertNotNull(extractJsonObject("""junk {"a": {"b": 2}} more"""))
        assertNull(extractJsonObject("[1, 2]"))
        assertNull(extractJsonObject("no braces"))
        assertNull(extractJsonObject("{broken"))
        assertNull(extractJsonObject(""))
    }

    // -- start -----------------------------------------------------------
    @Test
    fun startReportsProgressAndTheFilePath() = runBlocking {
        val staging = File(tmp.root, "staging")
        val runner = FakeRunner { call, onLine ->
            onLine("""[download] {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100}""")
            onLine("[Merger] Merging formats")
            File(staging, "${call.processId}.path").writeText("${staging.path}/Video [abc].mp4\n")
            RunResult(0, "", "")
        }
        val seen = CopyOnWriteArrayList<Progress>()
        val outcome = backend(runner).start(request(staging)) { seen.add(it) }.await()
        assertEquals(0, outcome.exitCode)
        assertEquals("${staging.path}/Video [abc].mp4", outcome.filePath)
        assertFalse(outcome.terminated)
        assertEquals(1, seen.size)
        assertEquals(50.0, seen[0].percent!!, 0.001)
        assertTrue("[Merger] Merging formats" in outcome.rawLog)
        assertFalse("downloaded_bytes" in outcome.rawLog)
        assertFalse("path file is removed after reading", File(staging, "item-1.path").exists())
    }

    @Test
    fun startPassesTheBuiltArgsAndCreatesTheStagingDirs() = runBlocking {
        val staging = File(tmp.root, "staging")
        val runner = FakeRunner { _, _ -> RunResult(0, "", "") }
        backend(runner).start(request(staging)) { }.await()
        val call = runner.calls.single()
        assertEquals(buildDownloadArgs(request(staging)), call.args)
        assertEquals("https://youtu.be/dQw4w9WgXcQ", call.url)
        assertEquals("item-1", call.processId)
        assertTrue(File(staging, "tmp").isDirectory)
    }

    @Test
    fun startDetectsAnAlreadyArchivedVideo() = runBlocking {
        val runner = FakeRunner { _, onLine ->
            onLine("[download] abc: has already been recorded in the archive")
            RunResult(0, "", "")
        }
        val outcome = backend(runner).start(request(File(tmp.root, "s"))) { }.await()
        assertNull(outcome.filePath)
        assertTrue(outcome.alreadyArchived)
    }

    @Test
    fun aStalePathFileFromAnEarlierAttemptIsIgnored() = runBlocking {
        val staging = File(tmp.root, "staging").also { it.mkdirs() }
        File(staging, "item-1.path").writeText("/stale.mp4\n")
        val runner = FakeRunner { _, _ -> RunResult(0, "", "") }
        val outcome = backend(runner).start(request(staging)) { }.await()
        assertNull(outcome.filePath)
    }

    @Test
    fun aFailingRunKeepsStderrInTheLogAndNoFile() = runBlocking {
        val runner = FakeRunner { _, onLine ->
            onLine("[youtube] abc: Downloading webpage")
            RunResult(1, "", "ERROR: HTTP Error 403: Forbidden")
        }
        val outcome = backend(runner).start(request(File(tmp.root, "s"))) { }.await()
        assertEquals(1, outcome.exitCode)
        assertNull(outcome.filePath)
        assertTrue("HTTP Error 403" in outcome.rawLog)
        assertTrue("Downloading webpage" in outcome.rawLog)
    }

    @Test
    fun cancelDestroysTheProcessAndMarksTheOutcomeTerminated() = runBlocking {
        val release = CountDownLatch(1)
        val started = CountDownLatch(1)
        val runner = FakeRunner { _, _ ->
            started.countDown()
            release.await(5, TimeUnit.SECONDS)
            RunResult(-1, "", "", canceled = true)
        }
        val handle = backend(runner).start(request(File(tmp.root, "s"))) { }
        assertTrue(started.await(5, TimeUnit.SECONDS))
        handle.cancel()
        assertEquals(listOf("item-1"), runner.destroyed.toList())
        release.countDown()
        val outcome = withTimeout(5000) { handle.await() }
        assertTrue(outcome.terminated)
        assertNull(outcome.filePath)
    }

    @Test
    fun cancelBeforeTheRunStartsNeverRunsYtDlp() = runBlocking {
        // A one-thread dispatcher kept busy, so the download job is queued behind it until released.
        val executor = Executors.newSingleThreadExecutor()
        val release = CountDownLatch(1)
        executor.submit { release.await(5, TimeUnit.SECONDS) }
        try {
            val runner = FakeRunner { _, _ -> RunResult(0, "", "") }
            val queuedScope = CoroutineScope(executor.asCoroutineDispatcher())
            val handle = YoutubeDlBackend(runner, queuedScope) { GB }.start(request(File(tmp.root, "s"))) { }
            handle.cancel()
            release.countDown()
            val outcome = withTimeout(5000) { handle.await() }
            assertTrue(outcome.terminated)
            assertNull(outcome.filePath)
            assertTrue(runner.calls.isEmpty())
        } finally {
            executor.shutdownNow()
        }
    }

    @Test
    fun aLineArrivingAfterCancelDestroysAgain() = runBlocking {
        val first = CountDownLatch(1)
        val go = CountDownLatch(1)
        val runner = FakeRunner { _, onLine ->
            first.countDown()
            go.await(5, TimeUnit.SECONDS)
            onLine("[download] late line")
            RunResult(-1, "", "", canceled = true)
        }
        val handle = backend(runner).start(request(File(tmp.root, "s"))) { }
        assertTrue(first.await(5, TimeUnit.SECONDS))
        handle.cancel()
        go.countDown()
        withTimeout(5000) { handle.await() }
        assertEquals(2, runner.destroyed.size)
    }

    @Test
    fun notEnoughFreeSpaceRefusesTheDownloadWithoutRunning() = runBlocking {
        val runner = FakeRunner { _, _ -> RunResult(0, "", "") }
        val outcome = backend(runner, free = 10L * 1024 * 1024).start(request(File(tmp.root, "s"))) { }.await()
        assertEquals(1, outcome.exitCode)
        assertTrue("No space left on device" in outcome.rawLog)
        assertTrue(runner.calls.isEmpty())
    }
}
