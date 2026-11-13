package com.desolate.elisium.engine

import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

/** In-memory HistoryStore following history.py semantics (finished_at stamping etc.). */
class FakeHistory : HistoryStore {
    private val rows = LinkedHashMap<Long, HistoryRecord>()
    private var next = 1L
    private val terminal = setOf("done", "failed", "skipped", "cancelled")

    /** Every `updateState` call as `recordId to state`, in order. */
    val stateLog = CopyOnWriteArrayList<Pair<Long, String>>()

    @Synchronized
    override fun add(
        url: String,
        videoKey: String?,
        title: String?,
        state: String,
        errorCode: String?,
        errorMessage: String?,
        filePath: String?,
    ): Long {
        require(url.isNotBlank())
        val id = next++
        rows[id] = HistoryRecord(
            id, url.trim(), videoKey, title, state, errorCode, errorMessage, filePath,
            "now", if (state in terminal) "now" else null,
        )
        return id
    }

    @Synchronized
    override fun updateState(
        recordId: Long,
        state: String,
        errorCode: String?,
        errorMessage: String?,
        filePath: String?,
        clearError: Boolean,
    ): Boolean {
        val old = rows[recordId] ?: return false
        stateLog.add(recordId to state)
        var row = old.copy(state = state)
        if (errorCode != null) row = row.copy(errorCode = errorCode)
        if (errorMessage != null) row = row.copy(errorMessage = errorMessage)
        if (clearError) row = row.copy(errorCode = null, errorMessage = null)
        if (filePath != null) row = row.copy(filePath = filePath)
        row = row.copy(finishedAt = if (state in terminal) (old.finishedAt ?: "now") else null)
        rows[recordId] = row
        return true
    }

    @Synchronized
    override fun get(recordId: Long): HistoryRecord? = rows[recordId]

    @Synchronized
    override fun search(text: String, limit: Int?): List<HistoryRecord> {
        val needle = text.trim()
        if (needle.isEmpty() || (limit != null && limit <= 0)) return emptyList()
        val hits = rows.values.reversed().filter {
            it.url.contains(needle) || (it.videoKey ?: "").contains(needle) || (it.title ?: "").contains(needle)
        }
        return if (limit == null) hits else hits.take(limit)
    }

    @Synchronized
    override fun recent(limit: Int): List<HistoryRecord> =
        if (limit <= 0) emptyList() else rows.values.reversed().take(limit)

    @Synchronized
    override fun delete(recordId: Long): Boolean = rows.remove(recordId) != null
}

/**
 * OutputStore fake. `publish` moves nothing unless [realDir] is set; it records the
 * published location and registers the video id found in the file name (`[id]`).
 */
class FakeStore(private val realDir: File? = null) : OutputStore {
    val existing: MutableSet<Pair<String, String>> = java.util.Collections.synchronizedSet(LinkedHashSet())
    val locations: MutableSet<String> = java.util.Collections.synchronizedSet(LinkedHashSet())
    val published = CopyOnWriteArrayList<Pair<File, String>>()
    val forgotten = CopyOnWriteArrayList<Pair<String, String>>()
    var failPublish = false
    var extractorForPublished = "youtube"

    override fun existsFor(extractorKey: String, videoId: String): Boolean =
        if (realDir != null) fileExistsFor(realDir, videoId) else (extractorKey to videoId) in existing

    override fun existsAt(location: String): Boolean =
        if (realDir != null) File(location).isFile else location in locations

    override suspend fun publish(stagedFile: File, displayName: String): PublishedFile? {
        published.add(stagedFile to displayName)
        if (failPublish) return null
        if (realDir != null) {
            realDir.mkdirs()
            val target = File(realDir, displayName)
            stagedFile.copyTo(target, overwrite = true)
            stagedFile.delete()
            return PublishedFile(target.path, displayName)
        }
        val location = "store://$displayName"
        locations.add(location)
        Regex("\\[([^\\]]+)]").find(displayName)?.let { existing.add(extractorForPublished to it.groupValues[1]) }
        return PublishedFile(location, displayName)
    }

    override fun forget(extractorKey: String, videoId: String) {
        forgotten.add(extractorKey to videoId)
    }

    /** Simulates the user deleting every finished file. */
    fun deleteEverything() {
        existing.clear()
        locations.clear()
        realDir?.listFiles()?.forEach { it.delete() }
    }
}

fun json(text: String): JsonObject = Json.parseToJsonElement(text) as JsonObject

/** A handle whose outcome the test (or [cancel]) controls. */
class FakeHandle(private val onCancel: (FakeHandle) -> Unit = {}) : DownloadHandle {
    val result = CompletableDeferred<DownloadOutcome>()

    @Volatile
    var cancelled = false

    override suspend fun await(): DownloadOutcome = result.await()

    override fun cancel() {
        cancelled = true
        onCancel(this)
        result.complete(DownloadOutcome(exitCode = -15, rawLog = "terminated", filePath = null, terminated = true))
    }

    fun finish(outcome: DownloadOutcome) {
        result.complete(outcome)
    }
}

/**
 * Backend fake. [probeHandler] answers `probe`; [startHandler] builds the handle for
 * each `start` (default: succeed immediately with a staged file named after the URL).
 */
class FakeBackend : DownloadBackend {
    var probeHandler: suspend (String) -> JsonObject = { json("""{"id": "x", "title": "Video title"}""") }
    var startHandler: (DownloadRequest, (Progress) -> Unit) -> DownloadHandle = { request, _ ->
        FakeHandle().also { it.finish(successOutcome(request)) }
    }
    val probes = CopyOnWriteArrayList<String>()
    val requests = CopyOnWriteArrayList<DownloadRequest>()
    private val startCount = AtomicInteger()

    val starts: Int get() = startCount.get()

    override suspend fun probe(url: String): ProbeResult {
        probes.add(url)
        return probeHandler(url)
    }

    override fun start(request: DownloadRequest, onProgress: (Progress) -> Unit): DownloadHandle {
        requests.add(request)
        startCount.incrementAndGet()
        return startHandler(request, onProgress)
    }
}

fun successOutcome(request: DownloadRequest, name: String = "Video [dQw4w9WgXcQ].mp4"): DownloadOutcome =
    DownloadOutcome(
        exitCode = 0,
        rawLog = "",
        filePath = File(request.stagingDir, name).path,
    )

fun failureOutcome(raw: String) = DownloadOutcome(exitCode = 1, rawLog = raw, filePath = null)
