package com.desolate.elisium.engine

import java.io.File
import kotlinx.serialization.json.JsonObject

/** The parsed `yt-dlp -J` object. */
typealias ProbeResult = JsonObject

/** Thrown by [DownloadBackend.probe] when yt-dlp fails; [raw] is its output. */
class ProbeFailure(val raw: String) : Exception("probe failed")

/** One progress report from a running download. */
data class Progress(
    /** `downloading`, `merging` or `converting`. */
    val stage: String,
    val status: String = "",
    /** Post-processor name when this is a post-processing report. */
    val postprocessor: String? = null,
    val downloadedBytes: Long? = null,
    val totalBytes: Long? = null,
    val speed: Double? = null,
    val eta: Double? = null,
    val percent: Double? = null,
)

data class DownloadRequest(
    val url: String,
    val formatSelector: String,
    val extraArgs: List<String>,
    val limitRate: String?,
    val archiveFile: File,
    /** Where yt-dlp writes (and keeps `.part` files between pause and resume). */
    val stagingDir: File,
    /** Unique per queue item, so a backend can find and stop the right process. */
    val processId: String,
)

data class DownloadOutcome(
    val exitCode: Int,
    val rawLog: String,
    /** The finished file yt-dlp reported (in the staging dir), or null. */
    val filePath: String?,
    /** yt-dlp exited 0 but downloaded nothing because the archive already had it. */
    val alreadyArchived: Boolean = false,
    /** The process was stopped by [DownloadHandle.cancel]. */
    val terminated: Boolean = false,
)

interface DownloadHandle {
    suspend fun await(): DownloadOutcome
    fun cancel()
}

interface DownloadBackend {
    @Throws(ProbeFailure::class)
    suspend fun probe(url: String): ProbeResult
    fun start(request: DownloadRequest, onProgress: (Progress) -> Unit): DownloadHandle
}

/** A file moved to its final place. [location] is a path or content URI. */
data class PublishedFile(val location: String, val displayName: String)

interface OutputStore {
    /** Is a finished file for this video already in the final location? */
    fun existsFor(extractorKey: String, videoId: String): Boolean

    /** Is a previously published file still at [location]? Unknown means true. */
    fun existsAt(location: String): Boolean = true

    /** Moves the finished file to its final place; null on failure. */
    suspend fun publish(stagedFile: File, displayName: String): PublishedFile?

    /** Forget any bookkeeping for a video whose file was deleted. */
    fun forget(extractorKey: String, videoId: String)
}

/** One history row, same fields as `history.py`. */
data class HistoryRecord(
    val id: Long,
    val url: String,
    val videoKey: String?,
    val title: String?,
    val state: String,
    val errorCode: String?,
    val errorMessage: String?,
    val filePath: String?,
    val createdAt: String,
    val finishedAt: String?,
)

interface HistoryStore {
    fun add(
        url: String,
        videoKey: String? = null,
        title: String? = null,
        state: String = "queued",
        errorCode: String? = null,
        errorMessage: String? = null,
        filePath: String? = null,
    ): Long

    /** Returns false for an unknown id. null error/file args leave the column alone. */
    fun updateState(
        recordId: Long,
        state: String,
        errorCode: String? = null,
        errorMessage: String? = null,
        filePath: String? = null,
        clearError: Boolean = false,
    ): Boolean

    fun get(recordId: Long): HistoryRecord?
    fun search(text: String, limit: Int? = 200): List<HistoryRecord>
    fun recent(limit: Int = 50): List<HistoryRecord>
    fun delete(recordId: Long): Boolean
}
