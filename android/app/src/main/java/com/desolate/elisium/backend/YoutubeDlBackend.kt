package com.desolate.elisium.backend

import com.desolate.elisium.engine.DownloadBackend
import com.desolate.elisium.engine.DownloadHandle
import com.desolate.elisium.engine.DownloadOutcome
import com.desolate.elisium.engine.DownloadRequest
import com.desolate.elisium.engine.ProbeFailure
import com.desolate.elisium.engine.ProbeResult
import com.desolate.elisium.engine.Progress
import com.desolate.elisium.engine.parseProgressLine
import com.desolate.elisium.storage.StorageSpace
import java.io.File
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

/**
 * [DownloadBackend] over a [YtDlpRunner] (youtubedl-android on a device).
 *
 * Everything here that is not the runner call is plain Kotlin and JVM-tested against a
 * fake runner; the real runner is compile-verified only.
 *
 * @param scope where the blocking process calls run (IO-capable).
 * @param freeBytes usable bytes where staging lives; the download is refused up front when
 *   there is not room for the file twice (see [StorageSpace]).
 */
class YoutubeDlBackend(
    private val runner: YtDlpRunner,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
    private val freeBytes: (File) -> Long = StorageSpace::freeBytes,
) : DownloadBackend {

    override suspend fun probe(url: String, cookiesFile: File?): ProbeResult = withContext(Dispatchers.IO) {
        val processId = "probe-" + UUID.randomUUID()
        val result = coroutineScope {
            val job = async(Dispatchers.IO) { runner.run(buildProbeArgs(url, cookiesFile), url, processId) { } }
            try {
                job.await()
            } catch (e: CancellationException) {
                runner.destroy(processId)
                throw e
            }
        }
        if (result.canceled) throw CancellationException("probe cancelled")
        val raw = result.stdout + result.stderr
        val errorText = classifiableText(result.stdout, result.stderr)
        if (result.exitCode != 0) throw ProbeFailure(raw, errorText)
        extractJsonObject(result.stdout) ?: throw ProbeFailure(raw, errorText)
    }

    override fun start(request: DownloadRequest, onProgress: (Progress) -> Unit): DownloadHandle {
        val handle = Handle(request.processId)
        handle.job = scope.async { handle.execute(request, onProgress) }
        return handle
    }

    private inner class Handle(private val processId: String) : DownloadHandle {
        private val terminated = AtomicBoolean(false)
        lateinit var job: Deferred<DownloadOutcome>

        override suspend fun await(): DownloadOutcome = job.await()

        override fun cancel() {
            terminated.set(true)
            runner.destroy(processId)
        }

        fun execute(request: DownloadRequest, onProgress: (Progress) -> Unit): DownloadOutcome {
            if (terminated.get()) return interpretOutcome(-1, "", null, terminated = true)
            val needed = StorageSpace.requiredFreeBytes(request.expectedBytes)
            val free = freeBytes(request.stagingDir)
            if (free < needed) {
                return interpretOutcome(
                    1, "No space left on device: $free bytes free, $needed needed for staging.", null, terminated = false,
                )
            }
            val pathFile = pathFileFor(request.stagingDir, request.processId)
            request.stagingDir.mkdirs()
            tempDirFor(request.stagingDir).mkdirs()
            pathFile.delete() // a stale file from an earlier attempt would be read as this run's result

            val lines = StringBuilder()
            val onLine = { raw: String ->
                if (terminated.get()) runner.destroy(processId) // closes the cancel-before-start race
                val line = raw.trimEnd('\r', '\n')
                val progress = parseProgressLine(line)
                if (progress != null) {
                    onProgress(progress)
                } else if (line.isNotBlank()) {
                    synchronized(lines) { lines.append(line).append('\n') }
                }
            }
            val result = runner.run(buildDownloadArgs(request), runnerUrlFor(request), processId, onLine)
            val log = synchronized(lines) { lines.toString() } + result.stderr
            val pathText = if (pathFile.exists()) pathFile.readText() else null
            pathFile.delete()
            val errorLog = classifiableText(synchronized(lines) { lines.toString() }, result.stderr)
            return interpretOutcome(result.exitCode, log.trimEnd(), pathText, terminated.get() || result.canceled, errorLog)
        }
    }
}

/** Port of `_json_object`: `-J` output parsed as one object, else the first object found in noise. */
fun extractJsonObject(text: String): JsonObject? {
    try {
        val whole = Json.parseToJsonElement(text)
        if (whole is JsonObject) return whole
    } catch (_: Exception) {
    }
    var start = text.indexOf('{')
    while (start != -1) {
        var end = text.lastIndexOf('}')
        while (end > start) {
            try {
                val value = Json.parseToJsonElement(text.substring(start, end + 1))
                if (value is JsonObject) return value
                break
            } catch (_: Exception) {
                end = text.lastIndexOf('}', end - 1)
            }
        }
        start = text.indexOf('{', start + 1)
    }
    return null
}
