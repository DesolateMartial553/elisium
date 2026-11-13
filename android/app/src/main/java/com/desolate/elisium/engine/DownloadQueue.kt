package com.desolate.elisium.engine

import java.io.File
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonObject

/*
 * Download queue (port of `queue.py`): concurrency, states, retry/backoff, archive
 * reconcile. States are the ones in core-spec/SPEC.md and are written through to
 * the HistoryStore.
 *
 * Dedupe identity is videoKey(url) (youtube:<id>) when available, else
 * normalizeUrl(url). Archive safety: every archive call is serialised behind one
 * lock and the archive is never rewritten while any item is downloading/merging/
 * converting (a read-only view is used instead).
 */

/** Retry schedule from the spec in milliseconds: wait 5s, 15s, 45s, then give up. */
val BACKOFF_MS: List<Long> = listOf(5_000L, 15_000L, 45_000L)

/** Only these error codes are retried (the spec says "on network errors"). */
val RETRYABLE_CODES: Set<String> = setOf("network")
val DOWNLOADING_STATES: Set<String> = setOf("downloading", "merging", "converting")
val ACTIVE_STATES: Set<String> = DOWNLOADING_STATES + "probing"
val TERMINAL_STATES: Set<String> = setOf("done", "failed", "skipped", "cancelled")
const val MAX_CONCURRENCY = 5
const val DEFAULT_CONCURRENCY = 2
const val DEFAULT_FORMAT = "bestvideo*+bestaudio/best"

val ALREADY_DOWNLOADED = ErrorInfo("Already downloaded.", "It is in the download folder", "already_downloaded")
private val UNKNOWN = ErrorInfo("Download failed.", "See Details", "unknown")
private val PUBLISH_FAILED = ErrorInfo("Could not save the file.", "Check free storage space", "publish_failed")

private fun checkConcurrency(value: Int): Int {
    require(value in 1..MAX_CONCURRENCY) { "concurrency must be between 1 and $MAX_CONCURRENCY, got $value" }
    return value
}

/** An immutable view of one queue item (what the UI and events carry). */
data class QueueItem(
    val id: Int,
    val recordId: Long,
    val url: String,
    val identity: String,
    val videoKey: String?,
    val state: String,
    val title: String?,
    val filePath: String?,
    val attempts: Int,
    val error: ErrorInfo?,
    val stage: String?,
    val downloadedBytes: Long?,
    val totalBytes: Long?,
    val speed: Double?,
    val eta: Double?,
    val percent: Double?,
)

sealed interface QueueEvent {
    data class Added(val item: QueueItem) : QueueEvent
    data class StateChanged(val id: Int, val state: String, val previous: String, val item: QueueItem) : QueueEvent
    data class ProgressChanged(val id: Int, val state: String, val item: QueueItem) : QueueEvent

    /** The title arrived (no state change). */
    data class ItemUpdated(val id: Int, val item: QueueItem) : QueueEvent
}

/** Archive view that can read but never rewrite the file (used while yt-dlp is appending to it). */
private class ReadOnlyArchive(private val archive: ArchiveView) : ArchiveView {
    override fun has(extractor: String, videoId: String): Boolean = archive.has(extractor, videoId)
    override fun remove(extractor: String, videoId: String): Boolean = false
}

private class Entry(
    val id: Int,
    val recordId: Long,
    val url: String,
    val identity: String,
    val videoKey: String?,
) {
    var state = "queued"
    var title: String? = null
    var filePath: String? = null
    var error: ErrorInfo? = null
    var attempts = 0
    var stage: String? = null
    var downloadedBytes: Long? = null
    var totalBytes: Long? = null
    var speed: Double? = null
    var eta: Double? = null
    var percent: Double? = null
    var handle: DownloadHandle? = null
    var owned = false
    var archiveKey: String? = null
    var formatSelector: String? = null
    var extraArgs: List<String>? = null

    fun snapshot() = QueueItem(
        id, recordId, url, identity, videoKey, state, title, filePath, attempts, error,
        stage, downloadedBytes, totalBytes, speed, eta, percent,
    )
}

/**
 * @param scope where item workers run (give it an IO-capable dispatcher on Android).
 * @param delay suspends for the given milliseconds; tests pass a virtual-time delay.
 * @param stagingDir where the backend writes (and keeps `.part` files across a pause).
 */
class DownloadQueue(
    private val history: HistoryStore,
    private val archive: Archive,
    private val outputStore: OutputStore,
    private val backend: DownloadBackend,
    private val stagingDir: File,
    private val scope: CoroutineScope,
    private val delay: suspend (Long) -> Unit = { kotlinx.coroutines.delay(it) },
    concurrency: Int = DEFAULT_CONCURRENCY,
    formatSelector: String = DEFAULT_FORMAT,
    limitRate: String? = null,
) {
    private var formatSelector: String = formatSelector
    private var limitRate: String? = limitRate
    private var extraArgs: List<String> = emptyList()
    private var concurrencyValue: Int = checkConcurrency(concurrency)

    private val entries = HashMap<Int, Entry>()
    private val order = ArrayList<Int>()
    private val byIdentity = HashMap<String, Int>()
    private var nextId = 1
    private var running = false

    // Lock order is always state lock -> archive lock (see isArchived).
    private val lock = ReentrantLock()
    private val archiveLock = ReentrantLock()

    private val _items = MutableStateFlow<List<QueueItem>>(emptyList())
    val items: StateFlow<List<QueueItem>> = _items.asStateFlow()

    private val _events = MutableSharedFlow<QueueEvent>(
        extraBufferCapacity = 8192,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val events: SharedFlow<QueueEvent> = _events.asSharedFlow()

    private val _idle = MutableStateFlow(true)

    // -- configuration ---------------------------------------------------
    /** Number of parallel downloads (1-5); the setter validates. */
    var concurrency: Int
        get() = lock.withLock { concurrencyValue }
        set(value) {
            val checked = checkConcurrency(value)
            lock.withLock { concurrencyValue = checked }
            schedule()
        }

    /** Sets `--limit-rate` (e.g. "2M"; null for no limit) for downloads that start afterwards. */
    fun setLimitRate(value: String?) = lock.withLock { limitRate = value?.ifEmpty { null } }

    fun setFormatSelector(selector: String) {
        require(selector.isNotEmpty()) { "format selector must be a non-empty string" }
        lock.withLock { formatSelector = selector }
    }

    fun setExtraArgs(args: List<String>) = lock.withLock { extraArgs = args.toList() }

    // -- reading ---------------------------------------------------------
    fun item(id: Int): QueueItem? = lock.withLock { entries[id]?.snapshot() }

    fun activeIds(): List<Int> = lock.withLock { order.filter { entries.getValue(it).state in ACTIVE_STATES } }

    /** Suspends until nothing is running or waiting to run. */
    suspend fun waitUntilIdle() {
        _idle.first { it }
    }

    // -- adding ----------------------------------------------------------
    /**
     * Queues [url]; a duplicate of an existing item returns that item unchanged.
     * [formatSelector] and [extraArgs] override the queue defaults for this item
     * only (an empty list is a real override); [title] is shown until the probe
     * supplies the real one.
     * @throws IllegalArgumentException for a URL that cannot be normalised.
     */
    fun add(
        url: String,
        formatSelector: String? = null,
        extraArgs: List<String>? = null,
        title: String? = null,
    ): QueueItem {
        require(url.isNotBlank()) { "url must be a non-empty string" }
        val clean = url.pyStrip()
        val normalised = normalizeUrl(clean)
        val key = videoKey(clean)
        val identity = key ?: normalised

        val snapshot = lock.withLock {
            val existing = byIdentity[identity]
            if (existing != null) {
                val found = entries.getValue(existing)
                if (found.state in setOf("done", "skipped") && !filePresent(found)) requeueMissing(found)
                return@withLock found.snapshot()
            }
            val recordId = history.add(clean, videoKey = identity, state = "queued")
            val entry = Entry(nextId, recordId, clean, identity, key)
            nextId++
            entry.title = title?.pyStrip()?.ifEmpty { null }
            entry.formatSelector = formatSelector?.ifEmpty { null }
            entry.extraArgs = extraArgs?.toList()
            entries[entry.id] = entry
            order.add(entry.id)
            byIdentity[identity] = entry.id
            val snap = entry.snapshot()
            _events.tryEmit(QueueEvent.Added(snap))
            publishState()
            snap
        }
        schedule()
        return snapshot
    }

    /** False only when we can tell the finished file is gone. */
    private fun filePresent(e: Entry): Boolean {
        val key = e.videoKey ?: e.archiveKey
        val path = e.filePath
        if (path == null && key == null) return true
        if (path != null && outputStore.existsAt(path)) return true
        if (key != null) {
            val (extractor, videoId) = splitKey(key) ?: return false
            if (outputStore.existsFor(extractor, videoId)) return true
        }
        return false
    }

    /**
     * Puts a done/skipped item whose file was deleted back to queued. Caller holds
     * the state lock. The stale archive entry is dropped only while no download is
     * active (yt-dlp appends to the archive and remove() rewrites it); otherwise it
     * stays and the attempt reconciles again later.
     */
    private fun requeueMissing(e: Entry) {
        val key = e.videoKey ?: e.archiveKey
        val parts = key?.let { splitKey(it) }
        if (parts != null) {
            try {
                outputStore.forget(parts.first, parts.second)
            } catch (_: Exception) {
            }
            if (!downloading()) {
                archiveLock.withLock {
                    try {
                        archive.remove(parts.first, parts.second)
                    } catch (_: Exception) {
                    }
                }
            }
        }
        e.error = null
        e.attempts = 0
        e.filePath = null
        resetProgress(e)
        setState(e, "queued", clearError = true)
    }

    // -- user actions ----------------------------------------------------
    /** Pauses one item. A download is cancelled; staged `.part` files stay. */
    fun pause(id: Int): Boolean {
        val result = lock.withLock {
            val e = entries[id] ?: return@withLock false
            when {
                e.state in ACTIVE_STATES -> {
                    val handle = e.handle
                    setState(e, "paused")
                    handle?.cancel()
                    true
                }
                e.state == "queued" -> {
                    setState(e, "paused")
                    true
                }
                else -> false
            }
        }
        schedule()
        return result
    }

    /** Queues a paused item again; the download reruns and continues the `.part` files. */
    fun resume(id: Int): Boolean {
        val result = lock.withLock {
            val e = entries[id]
            if (e == null || e.state != "paused") return@withLock false
            e.error = null
            e.percent = null
            setState(e, "queued", clearError = true)
            true
        }
        schedule()
        return result
    }

    /** Puts a failed or cancelled item back in the queue, backoff reset. */
    fun retry(id: Int): Boolean {
        val result = lock.withLock {
            val e = entries[id]
            if (e == null || e.state != "failed" && e.state != "cancelled") return@withLock false
            e.error = null
            e.attempts = 0
            e.percent = null
            setState(e, "queued", clearError = true)
            true
        }
        schedule()
        return result
    }

    /** Cancels one item; a running download is cancelled. */
    fun cancel(id: Int): Boolean {
        val result = lock.withLock {
            val e = entries[id]
            if (e == null || e.state in TERMINAL_STATES) return@withLock false
            val handle = e.handle
            e.error = null
            setState(e, "cancelled", clearError = true)
            handle?.cancel()
            true
        }
        schedule()
        return result
    }

    // -- lifecycle -------------------------------------------------------
    /** Starts scheduling (idempotent). */
    fun start() {
        lock.withLock { running = true }
        schedule()
    }

    /** Stops scheduling and pauses everything that was running. */
    fun stop() {
        lock.withLock {
            running = false
            val handles = ArrayList<DownloadHandle>()
            for (e in entries.values) {
                if (e.state in ACTIVE_STATES) {
                    e.handle?.let { handles.add(it) }
                    setState(e, "paused")
                }
            }
            handles.forEach { it.cancel() }
            publishState()
        }
    }

    // -- internals: state ------------------------------------------------
    private fun resetProgress(e: Entry) {
        e.percent = null
        e.stage = null
        e.downloadedBytes = null
        e.totalBytes = null
        e.speed = null
        e.eta = null
    }

    /** Caller holds the lock. */
    private fun publishState() {
        _items.value = order.map { entries.getValue(it).snapshot() }
        _idle.value = entries.values.none { it.owned || it.state in ACTIVE_STATES || it.state == "queued" }
    }

    /** Moves [e] to [state], writes it to history, emits the event. Caller holds the lock. */
    private fun setState(
        e: Entry,
        state: String,
        error: ErrorInfo? = null,
        filePath: String? = null,
        clearError: Boolean = false,
    ) {
        val previous = e.state
        if (previous == state) return
        e.state = state
        history.updateState(
            e.recordId,
            state,
            errorCode = error?.code,
            errorMessage = error?.message,
            filePath = filePath,
            clearError = clearError,
        )
        _events.tryEmit(QueueEvent.StateChanged(e.id, state, previous, e.snapshot()))
        publishState()
    }

    private fun downloading(): Boolean = entries.values.any { it.state in DOWNLOADING_STATES }

    // -- internals: scheduling -------------------------------------------
    private fun schedule() {
        lock.withLock {
            while (running && entries.values.count { it.owned } < concurrencyValue) {
                val next = order.map { entries.getValue(it) }.firstOrNull { it.state == "queued" && !it.owned } ?: break
                // Claim the slot before the worker starts so we cannot over-fill.
                next.owned = true
                scope.launch { work(next) }
            }
            publishState()
        }
    }

    private suspend fun work(e: Entry) {
        try {
            runItem(e)
        } catch (c: CancellationException) {
            lock.withLock { e.handle }?.cancel()
            throw c
        } catch (_: Exception) {
            lock.withLock {
                if (e.state in ACTIVE_STATES || e.state == "queued") {
                    e.error = UNKNOWN
                    setState(e, "failed", error = UNKNOWN)
                }
            }
        } finally {
            lock.withLock {
                e.owned = false
                e.handle = null
            }
            schedule()
        }
    }

    private suspend fun runItem(e: Entry) {
        while (true) {
            val wait = attempt(e) ?: return
            delay(wait)
            lock.withLock {
                if (!running || e.state != "queued" || !e.owned) return
            }
        }
    }

    // -- internals: one attempt ------------------------------------------
    /**
     * Probes, reconciles, downloads once. Returns null when the item is finished
     * with (terminal, paused or stopped) or the milliseconds to wait before the next attempt.
     */
    private suspend fun attempt(e: Entry): Long? {
        lock.withLock {
            if (!running || e.state != "queued" || !e.owned) return null
            e.error = null
            resetProgress(e)
            e.stage = null
            setState(e, "probing")
        }

        var info: JsonObject? = null
        var error: ErrorInfo? = null
        try {
            info = backend.probe(e.url)
        } catch (f: ProbeFailure) {
            error = explain(f.raw)
        } catch (c: CancellationException) {
            throw c
        } catch (_: Exception) {
            error = UNKNOWN
        }
        if (info != null) {
            learnArchiveKey(e, info)
            val title = titleFrom(info)
            if (title != null) {
                lock.withLock {
                    e.title = title
                    _events.tryEmit(QueueEvent.ItemUpdated(e.id, e.snapshot()))
                    publishState()
                }
            }
        }

        if (error == null) {
            lock.withLock {
                if (!running || e.state != "probing") return null // paused or cancelled while probing
            }
            if (isArchived(e)) {
                lock.withLock {
                    if (e.state == "probing") {
                        e.error = ALREADY_DOWNLOADED
                        setState(e, "skipped", error = ALREADY_DOWNLOADED)
                    }
                }
                return null
            }
            lock.withLock {
                if (!running || e.state != "probing") return null
                setState(e, "downloading")
            }
            error = download(e)
        }
        if (error == null) return null
        return afterFailure(e, error)
    }

    private fun learnArchiveKey(e: Entry, info: JsonObject) {
        if (e.videoKey != null) return
        val extractor = stringOf(info["extractor_key"]) ?: stringOf(info["extractor"])
        val videoId = stringOf(info["id"])
        if (extractor != null && videoId != null &&
            extractor.pyStrip().isNotEmpty() && videoId.pyStrip().isNotEmpty() &&
            (extractor + videoId).none { isPySpace(it) }
        ) {
            lock.withLock { e.archiveKey = "${extractor.lowercase()}:$videoId" }
        }
    }

    /** A non-empty JSON string, else null (Python's `value or other` on strings). */
    private fun stringOf(el: JsonElement?): String? =
        if (el is JsonPrimitive && el.isString && el.content.isNotEmpty()) el.content else null

    private fun titleFrom(info: JsonObject): String? {
        val el = info["title"]
        if (el is JsonPrimitive && el.isString && el.content.pyStrip().isNotEmpty()) return el.content.pyStrip()
        return null
    }

    private fun afterFailure(e: Entry, error: ErrorInfo): Long? = lock.withLock {
        if (!running || e.state in TERMINAL_STATES || e.state == "paused") return@withLock null
        e.error = error
        if (error.code in RETRYABLE_CODES && e.attempts < BACKOFF_MS.size) {
            val wait = BACKOFF_MS[e.attempts]
            e.attempts++
            // Back to queued while waiting, but keep the worker slot: the scheduler
            // only picks items that no worker owns.
            setState(e, "queued")
            return@withLock wait
        }
        setState(e, "failed", error = error)
        null
    }

    /**
     * Runs one download. Returns null on success and on a user pause/cancel, and an
     * [ErrorInfo] for a real failure.
     */
    private suspend fun download(e: Entry): ErrorInfo? {
        val request = lock.withLock {
            DownloadRequest(
                url = e.url,
                formatSelector = e.formatSelector ?: formatSelector,
                extraArgs = e.extraArgs ?: extraArgs,
                limitRate = limitRate,
                archiveFile = archive.file,
                stagingDir = stagingDir,
                processId = "item-${e.id}",
            )
        }
        val outcome: DownloadOutcome = try {
            stagingDir.mkdirs()
            val handle = backend.start(request) { progress -> onProgress(e, progress) }
            val stopNow = lock.withLock {
                e.handle = handle
                e.state == "paused" || e.state == "cancelled"
            }
            if (stopNow) handle.cancel()
            try {
                handle.await()
            } catch (c: CancellationException) {
                handle.cancel()
                throw c
            }
        } catch (c: CancellationException) {
            throw c
        } catch (_: Exception) {
            lock.withLock {
                e.handle = null
                if (e.state == "paused" || e.state == "cancelled") return null
            }
            return UNKNOWN
        }

        lock.withLock {
            e.handle = null
            if (e.state == "paused" || e.state == "cancelled") return null
        }

        if (outcome.exitCode == 0 && !outcome.terminated) {
            val reported = outcome.filePath
            if (reported == null && outcome.alreadyArchived) {
                // yt-dlp exited 0 but downloaded nothing: the archive had it.
                lock.withLock {
                    if (e.state in DOWNLOADING_STATES) {
                        e.error = ALREADY_DOWNLOADED
                        setState(e, "skipped", error = ALREADY_DOWNLOADED)
                    }
                }
                return null
            }
            var finalPath: String? = null
            if (reported != null) {
                val staged = File(reported)
                val published = try {
                    outputStore.publish(staged, staged.name)
                } catch (c: CancellationException) {
                    throw c
                } catch (_: Exception) {
                    null
                }
                if (published == null) return PUBLISH_FAILED
                finalPath = published.location
            }
            lock.withLock {
                if (e.state in DOWNLOADING_STATES) {
                    e.filePath = finalPath
                    e.percent = 100.0
                    e.error = null
                    setState(e, "done", filePath = finalPath, clearError = true)
                }
            }
            return null
        }
        return explain(outcome.rawLog)
    }

    private fun onProgress(e: Entry, p: Progress) {
        lock.withLock {
            if (e.state in TERMINAL_STATES || e.state == "paused") return
            val housekeeping = p.postprocessor != null && p.stage == "downloading"
            if (p.stage in STAGES && e.state != p.stage && !housekeeping) setState(e, p.stage)
            e.stage = p.stage
            p.downloadedBytes?.let { e.downloadedBytes = it }
            p.totalBytes?.let { e.totalBytes = it }
            p.speed?.let { e.speed = it }
            p.eta?.let { e.eta = it }
            p.percent?.let { e.percent = it }
            _events.tryEmit(QueueEvent.ProgressChanged(e.id, e.state, e.snapshot()))
            publishState()
        }
    }

    // -- internals: archive + output -------------------------------------
    /**
     * True when this video is archived and its file is still there. Held under both
     * locks: the state lock stops an item starting a download in the middle of an
     * archive rewrite, and the archive lock serialises every archive access.
     */
    private fun isArchived(e: Entry): Boolean {
        val key = e.videoKey ?: e.archiveKey ?: return false
        return lock.withLock {
            archiveLock.withLock {
                val view: ArchiveView = if (downloading()) ReadOnlyArchive(archive) else archive
                reconcile(view, key) { extractor, videoId -> outputStore.existsFor(extractor, videoId) }
            }
        }
    }
}
