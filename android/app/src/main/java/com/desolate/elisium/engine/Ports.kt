package com.desolate.elisium.engine

import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** The parsed `yt-dlp -J` object. */
typealias ProbeResult = JsonObject

/** Thrown by [DownloadBackend.probe] when yt-dlp fails; [raw] is its output. */
class ProbeFailure(val raw: String, val errorText: String = raw) : Exception("probe failed")

/** Thrown by an [OutputStore] when Android denies the permission needed to save into the public folder (API 26-28). */
class StoragePermissionException : Exception("storage permission denied")

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
    /** Best size estimate from the probe (`filesize` / `filesize_approx`), or null when unknown. */
    val expectedBytes: Long? = null,
    /**
     * The imported `cookies.txt` to pass as `--cookies`, or null. Only the path is kept: the app
     * never reads, copies or logs the cookie contents.
     */
    val cookiesFile: File? = null,
    /**
     * The probe's info JSON (`--load-info-json`). When set the link is NOT passed to yt-dlp: it loads this lookup
     * instead of looking the link up again. Null runs from the link exactly as before.
     */
    val infoJson: File? = null,
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
    /** What error classification reads: stderr and `ERROR:`/`WARNING:` lines, never titles printed on stdout. */
    val errorLog: String = rawLog,
)

interface DownloadHandle {
    suspend fun await(): DownloadOutcome
    fun cancel()
}

interface DownloadBackend {
    /** Probes [url]; [cookiesFile] is passed on when the site needs a signed-in session. */
    @Throws(ProbeFailure::class)
    suspend fun probe(url: String, cookiesFile: File? = null): ProbeResult
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

    /**
     * Moves the finished file into the owner's subfolder of the output location (media engine files:
     * `Download/Elisium/<owner>/`). The default ignores [subfolder] and saves flat, so a store that has
     * not learned folders yet still works.
     */
    suspend fun publish(stagedFile: File, displayName: String, subfolder: String?): PublishedFile? =
        publish(stagedFile, displayName)

    /** Is a finished file whose name contains `[<videoId>]` already in [subfolder] (flat by default)? */
    fun existsInFolder(subfolder: String?, videoId: String): Boolean = existsFor("", videoId)

    /** Deletes a file this store published (used when the item was cancelled during the copy). False when unsupported. */
    fun delete(location: String): Boolean = false

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
    /** A plain-words line the post's row shows (for example "Already saved"); null for older rows. */
    val note: String? = null,
    /** How many files the post had; null for single-file downloads and older rows. */
    val filesTotal: Int? = null,
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

    /** Stores the post's [note] and [filesTotal]; false for an unknown id (or a store without these columns). */
    fun updateExtras(recordId: Long, note: String?, filesTotal: Int?): Boolean = false

    fun get(recordId: Long): HistoryRecord?
    fun search(text: String, limit: Int? = 200): List<HistoryRecord>
    fun recent(limit: Int = 50): List<HistoryRecord>
    fun delete(recordId: Long): Boolean
}

/** Best size estimate (bytes) from a probe object: `filesize`, else `filesize_approx`. */
fun expectedBytesFrom(info: JsonObject): Long? {
    for (key in listOf("filesize", "filesize_approx")) {
        val el = info[key] as? JsonPrimitive ?: continue
        val v = el.content.toDoubleOrNull() ?: continue
        if (v > 0) return v.toLong()
    }
    return null
}
