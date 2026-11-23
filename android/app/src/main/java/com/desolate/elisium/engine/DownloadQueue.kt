package com.desolate.elisium.engine

import com.desolate.elisium.media.CancelToken
import com.desolate.elisium.media.MediaEngine
import com.desolate.elisium.media.MediaRoute
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import com.desolate.elisium.media.routeFor
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
internal val PUBLISH_FAILED = ErrorInfo("Could not save the file.", "Check free storage space", "publish_failed")
internal val STORAGE_PERMISSION = ErrorInfo("Elisium needs storage permission to save files.", "Allow storage access in Settings, then tap Retry", "storage_permission")

/** History id used when the database refused the insert (disk full): the item still runs from memory. */
private const val NO_RECORD = -1L

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
    /** The card's picture (http/https link): from the yt-dlp probe or the media plan. Display only, never in history. */
    val thumbnail: String? = null,
    /** "6 photos + song" or "1080p MP4": the kind of download, in plain words (display only). */
    val formatLabel: String? = null,
    /** Media engine items only: files finished / planned (null for yt-dlp items). */
    val filesDone: Int? = null,
    val filesTotal: Int? = null,
    /** A plain-words line under the card ("Already saved", a song note). */
    val note: String? = null,
    /** Why the item may sit at "Starting" ([WAIT_RATE_LIMITED], [WAIT_NETWORK], [WAIT_SIGNING_IN]), or null. Display only. */
    val waitHint: String? = null,
    /** Queue-clock time (ms) the state or the progress last changed: the UI shows a reason after 10 quiet seconds. */
    val quietSince: Long? = null,
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
    private val hintFor: (Entry) -> String?,
) {
    /** Which site this link belongs to (rate limiting is per site). */
    val site: String = siteKey(url)
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
    var thumbnail: String? = null
    var formatLabel: String? = null
    var filesDone: Int? = null
    var filesTotal: Int? = null
    var note: String? = null
    var quietSince: Long? = null

    /** Steadier speed and time left for the file being downloaded (null until a download starts). */
    var smoother: SpeedSmoother? = null

    /** "Download again anyway": the media archive is ignored for this item's runs. */
    var force = false

    /** yt-dlp said `no_media` once: later attempts go straight to the media engine. */
    var mediaOnly = false
    var handle: DownloadHandle? = null
    var owned = false
    var archiveKey: String? = null
    var formatSelector: String? = null
    var extraArgs: List<String>? = null
    var expectedBytes: Long? = null

    /** Identifies the running attempt, so progress from an older, dying process is ignored. */
    var token: Any? = null

    fun snapshot() = QueueItem(
        id, recordId, url, identity, videoKey, state, title, filePath, attempts, error,
        stage, downloadedBytes, totalBytes, speed, eta, percent,
        thumbnail, formatLabel, filesDone, filesTotal, note, hintFor(this), quietSince,
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
    /** The media engine's own archive (`media-archive.txt` beside the yt-dlp one: yt-dlp never writes to it). */
    private val mediaArchive: Archive = Archive(File(archive.file.absoluteFile.parentFile ?: File("."), "media-archive.txt")),
    /** Milliseconds now; tests pass a fake so the smoothed time left and the quiet stamps are exact. */
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private var formatSelector: String = formatSelector
    private var limitRate: String? = limitRate
    private var extraArgs: List<String> = emptyList()
    private var cookiesFile: File? = null
    private var mediaEngine: MediaEngine? = null
    private var photoMode: PhotoMode = PhotoMode.PhotosSongVideo
    private var songLength: SongLength = SongLength.Snippet
    private var concurrencyValue: Int = checkConcurrency(concurrency)

    /** "Faster downloads: Auto" (true) lets a download load the probe's info instead of looking the link up again. */
    private var reuseProbe: Boolean = true

    /** Sites that answered 429 this session: no probe reuse for them and one download at a time. */
    private val limitedSites = HashSet<String>()

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

    /** Settings > Downloads > Faster downloads: Auto (true) or Off (false), for downloads that start afterwards. */
    fun setReuseProbe(enabled: Boolean) = lock.withLock { reuseProbe = enabled }

    fun setExtraArgs(args: List<String>) = lock.withLock { extraArgs = args.toList() }

    /**
     * Sets the imported `cookies.txt` for probes and downloads that start afterwards (null clears
     * it). Only the path is held; the app never reads, copies or logs the cookie contents, and the
     * path never reaches history.
     */
    fun setCookiesFile(file: File?) = lock.withLock { cookiesFile = file }

    /** Turns on the media engine (photo posts, carousels, stories, TikTok slideshows); null turns it off. */
    fun setMediaEngine(engine: MediaEngine?) = lock.withLock { mediaEngine = engine }

    /** "Photo posts with a song" for runs that start afterwards. */
    fun setPhotoMode(mode: PhotoMode) = lock.withLock { photoMode = mode }

    /** "Song length" for runs that start afterwards. */
    fun setSongLength(length: SongLength) = lock.withLock { songLength = length }

    /** The cookies file when it is really there: yt-dlp must not be told to read a missing path. */
    private fun activeCookiesFile(): File? = lock.withLock { cookiesFile?.takeIf { it.isFile } }

    // -- reading ---------------------------------------------------------
    fun item(id: Int): QueueItem? = lock.withLock { entries[id]?.snapshot() }

    fun activeIds(): List<Int> = lock.withLock { order.filter { entries.getValue(it).state in ACTIVE_STATES } }

    /** Suspends until nothing is running or waiting to run. */
    suspend fun waitUntilIdle() {
        _idle.first { it }
    }

    // -- adding ----------------------------------------------------------
    /**
     * Queues [url]; a duplicate of an existing item returns that item. A duplicate whose item is
     * failed or cancelled is retried (queued again, backoff reset); a done or skipped one whose
     * file is gone downloads again; anything else is left alone.
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
        force: Boolean = false,
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
                if (force && found.state in TERMINAL_STATES && routeFor(found.url) != MediaRoute.YTDLP) {
                    // "Download again anyway": a photo post or story runs again without the media archive.
                    found.force = true
                    requeueMissing(found)
                } else if (found.state in setOf("done", "skipped") && !filePresent(found)) {
                    requeueMissing(found)
                } else if (found.state == "failed" || found.state == "cancelled") {
                    requeueFinished(found) // pasting a failed or cancelled link again means "try again"
                }
                return@withLock found.snapshot()
            }
            val recordId = try {
                history.add(clean, videoKey = identity, state = "queued")
            } catch (_: Exception) {
                NO_RECORD // disk full or a broken database must not lose the download
            }
            val entry = Entry(nextId, recordId, clean, identity, key) { waitHintFor(it) }
            entry.quietSince = clock()
            nextId++
            entry.title = title?.pyStrip()?.ifEmpty { null }
            entry.formatSelector = formatSelector?.ifEmpty { null }
            entry.extraArgs = extraArgs?.toList()
            entry.force = force && routeFor(clean) != MediaRoute.YTDLP
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

    /** Puts a failed or cancelled item back in the queue, backoff reset. Caller holds the state lock. */
    private fun requeueFinished(e: Entry) {
        e.error = null
        e.attempts = 0
        e.percent = null
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
            requeueFinished(e)
            true
        }
        schedule()
        return result
    }

    /** Cancels one item; a running download is cancelled. */
    fun cancel(id: Int): Boolean {
        var leftovers: StageRef? = null
        val result = lock.withLock {
            val e = entries[id]
            if (e == null || e.state in TERMINAL_STATES) return@withLock false
            val handle = e.handle
            e.error = null
            // A worker that owns the item deletes the files itself once its process is gone.
            if (!e.owned) leftovers = stageRef(e)
            setState(e, "cancelled", clearError = true)
            handle?.cancel()
            true
        }
        leftovers?.let { cleanupStaging(it, keepPartial = false) }
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
        e.filesDone = null
        e.filesTotal = null
        e.note = null
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
        e.quietSince = clock()
        try {
            history.updateState(
                e.recordId,
                state,
                errorCode = error?.code,
                errorMessage = error?.message,
                filePath = filePath,
                clearError = clearError,
            )
        } catch (_: Exception) {
            // Disk full or a broken database: the in-memory state stays authoritative.
        }
        _events.tryEmit(QueueEvent.StateChanged(e.id, state, previous, e.snapshot()))
        publishState()
    }

    private fun downloading(): Boolean = entries.values.any { it.state in DOWNLOADING_STATES }

    /** Why [e] may sit at "Starting": rate limited site > retrying after a network error > signing in. Caller holds the lock. */
    private fun waitHintFor(e: Entry): String? {
        if (e.state in TERMINAL_STATES || e.state == "paused") return null
        return waitHint(
            rateLimited = e.site in limitedSites,
            retryingNetwork = e.attempts > 0 && e.error?.code == "network",
            signedIn = cookiesFile != null && isSignedInSite(e.url),
        )
    }

    // -- internals: staging cleanup ----------------------------------------
    private class StageRef(val processId: String, val videoId: String?, val identity: String)

    /** Caller holds the state lock. */
    private fun stageRef(e: Entry) =
        StageRef("item-${e.id}", (e.videoKey ?: e.archiveKey)?.let { splitKey(it)?.second }, e.identity)

    private fun cleanupStaging(ref: StageRef, keepPartial: Boolean) {
        try {
            deleteItemLeftovers(stagingDir, ref.processId, ref.videoId, keepPartial)
            if (!keepPartial) deleteDirectory(mediaDirFor(stagingDir, ref.identity))
        } catch (_: Exception) {
        }
    }

    // -- internals: scheduling -------------------------------------------
    private fun schedule() {
        lock.withLock {
            while (running && entries.values.count { it.owned } < concurrencyValue) {
                // A site that answered 429 runs one download at a time: its other items wait, the rest go on.
                val ownedSites = entries.values.filter { it.owned }.map { it.site }
                val next = order.map { entries.getValue(it) }
                    .firstOrNull { it.state == "queued" && !it.owned && siteSlotFree(it.site, limitedSites, ownedSites) } ?: break
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
        } catch (x: Exception) {
            val unknown = withCause(UNKNOWN, sanitizeCause(x))
            lock.withLock {
                if (e.state in ACTIVE_STATES || e.state == "queued") {
                    e.error = unknown
                    setState(e, "failed", error = unknown)
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
        if (routeOf(e) == MediaRoute.MEDIA) return runMediaAttempt(e)

        var info: JsonObject? = null
        var probedAt = 0L
        var error: ErrorInfo? = null
        try {
            info = backend.probe(e.url, activeCookiesFile())
            probedAt = clock()
        } catch (f: ProbeFailure) {
            // Same wording rules as a failed download: the site, not "Instagram".
            error = withCause(explain(f.errorText, e.url, activeCookiesFile() != null), lastLogLine(f.errorText.ifBlank { f.raw }))
        } catch (c: CancellationException) {
            throw c
        } catch (x: Exception) {
            error = withCause(UNKNOWN, sanitizeCause(x))
        }
        if (info != null) {
            learnArchiveKey(e, info)
            expectedBytesFrom(info)?.let { bytes -> lock.withLock { e.expectedBytes = bytes } }
            val title = titleFrom(info)
            val thumbnail = thumbnailFrom(info)
            val label = formatLabelFrom(info, lock.withLock { e.extraArgs ?: extraArgs })
            if (title != null || thumbnail != null || label != null) {
                lock.withLock {
                    if (title != null) e.title = title
                    e.thumbnail = thumbnail ?: e.thumbnail
                    e.formatLabel = label ?: e.formatLabel
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
                var leftovers: StageRef? = null
                lock.withLock {
                    if (e.state == "probing") {
                        e.error = ALREADY_DOWNLOADED
                        leftovers = stageRef(e)
                        setState(e, "skipped", error = ALREADY_DOWNLOADED)
                    }
                }
                leftovers?.let { cleanupStaging(it, keepPartial = false) }
                return null
            }
            lock.withLock {
                if (!running || e.state != "probing") return null
                setState(e, "downloading")
            }
            error = download(e, info, probedAt)
        }
        if (error == null) return null
        if ((error.code == "no_media" || error.code == "unknown") && routeOf(e) == MediaRoute.YTDLP_THEN_MEDIA) {
            // yt-dlp found no video in the post (or failed in a way it cannot name, which on a photo post is
            // usually Instagram's sign-in wall): the same attempt re-runs once on the media engine (no retry counted).
            val switched = lock.withLock {
                if (running && e.state in ACTIVE_STATES) {
                    e.mediaOnly = true
                    if (e.state != "probing") setState(e, "probing")
                    true
                } else {
                    false
                }
            }
            if (switched) return runMediaAttempt(e)
        }
        return afterFailure(e, error)
    }

    private fun routeOf(e: Entry): MediaRoute = lock.withLock {
        when {
            mediaEngine == null -> MediaRoute.YTDLP
            e.mediaOnly -> MediaRoute.MEDIA
            else -> routeFor(e.url)
        }
    }

    /**
     * The media-engine attempt (state is `probing`): photo posts, carousels, stories, highlights and TikTok
     * slideshows. Same contract as [download]: null on success or a user pause/cancel, else the error.
     */
    private suspend fun runMediaAttempt(e: Entry): Long? {
        val engine = lock.withLock { mediaEngine } ?: return afterFailure(e, UNKNOWN)
        val cancelToken = CancelToken()
        val attemptToken = Any()
        val cookies = activeCookiesFile()
        val request = lock.withLock {
            if (!running || e.state != "probing") return null
            e.token = attemptToken
            e.handle = object : DownloadHandle {
                override suspend fun await(): DownloadOutcome = throw UnsupportedOperationException("media items run inline")
                override fun cancel() = cancelToken.cancel()
            }
            MediaRunRequest(e.url, cookies, e.force, photoMode, songLength, mediaDirFor(stagingDir, e.identity))
        }
        val hooks = object : MediaHooks {
            override fun planned(title: String?, thumbnail: String?, formatLabel: String?, filesTotal: Int): Boolean =
                lock.withLock {
                    if (!running || e.state != "probing") return@withLock false
                    title?.let { e.title = it }
                    e.thumbnail = thumbnail ?: e.thumbnail
                    e.formatLabel = formatLabel ?: e.formatLabel
                    e.filesDone = 0
                    e.filesTotal = filesTotal
                    _events.tryEmit(QueueEvent.ItemUpdated(e.id, e.snapshot()))
                    setState(e, "downloading")
                    true
                }

            override fun progress(done: Int, total: Int) {
                lock.withLock {
                    if (e.token !== attemptToken || e.state !in ACTIVE_STATES) return
                    e.filesDone = done
                    e.filesTotal = total
                    e.quietSince = clock()
                    e.percent = if (total > 0) (done * 100.0 / total).coerceAtMost(100.0) else null
                    _events.tryEmit(QueueEvent.ProgressChanged(e.id, e.state, e.snapshot()))
                    publishState()
                }
            }

            override fun converting() {
                lock.withLock {
                    if (e.token === attemptToken && e.state in DOWNLOADING_STATES) {
                        e.stage = "converting"
                        setState(e, "converting")
                    }
                }
            }

            override fun stopped(): Boolean = lock.withLock { !running || e.state !in ACTIVE_STATES }
        }
        val outcome: MediaOutcome = try {
            stagingDir.mkdirs()
            MediaRunner(engine, mediaArchive, outputStore).run(request, hooks, cancelToken)
        } catch (c: CancellationException) {
            cancelToken.cancel()
            throw c
        } catch (x: Exception) {
            MediaOutcome.Failed(withCause(UNKNOWN, sanitizeCause(x)))
        }

        var ref: StageRef? = null
        val verdict = lock.withLock {
            e.handle = null
            e.token = null
            ref = stageRef(e)
            when {
                outcome is MediaOutcome.Done || outcome is MediaOutcome.Skipped -> 0 // already moved: the item is finished
                e.state == "cancelled" -> 2
                e.state == "paused" || e.state == "queued" -> 1
                else -> 0
            }
        }
        if (verdict == 2) ref?.let { cleanupStaging(it, keepPartial = false) }
        if (verdict != 0) return null
        when (outcome) {
            is MediaOutcome.Stopped -> return null
            is MediaOutcome.Failed -> return afterFailure(e, outcome.error)
            is MediaOutcome.Done -> lock.withLock {
                if (e.state !in TERMINAL_STATES) {
                    e.filePath = outcome.firstLocation
                    e.percent = 100.0
                    e.filesTotal = outcome.filesTotal
                    e.filesDone = outcome.filesTotal
                    e.note = outcome.note
                    e.error = null
                    e.force = false
                    setState(e, "done", filePath = outcome.firstLocation, clearError = true)
                    saveExtras(e)
                }
            }
            is MediaOutcome.Skipped -> lock.withLock {
                if (e.state !in TERMINAL_STATES) {
                    e.error = ALREADY_DOWNLOADED
                    e.filesTotal = outcome.filesTotal
                    e.note = outcome.note
                    e.force = false
                    setState(e, "skipped", error = ALREADY_DOWNLOADED)
                    saveExtras(e)
                }
            }
        }
        return null
    }

    /** Writes the post's note and file count to its history row. Caller holds the state lock. */
    private fun saveExtras(e: Entry) {
        try {
            history.updateExtras(e.recordId, e.note, e.filesTotal)
        } catch (_: Exception) {
        }
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

    private fun afterFailure(e: Entry, error: ErrorInfo): Long? {
        var leftovers: StageRef? = null
        val wait = lock.withLock {
            if (!running || e.state in TERMINAL_STATES || e.state == "paused") return@withLock null
            e.error = error
            if (isRateLimitCode(error.code)) limitedSites.add(e.site) // this site now runs one at a time, no probe reuse
            if (error.code in RETRYABLE_CODES && e.attempts < BACKOFF_MS.size) {
                val wait = BACKOFF_MS[e.attempts]
                e.attempts++
                // Back to queued while waiting, but keep the worker slot: the scheduler
                // only picks items that no worker owns.
                setState(e, "queued")
                return@withLock wait
            }
            leftovers = stageRef(e)
            setState(e, "failed", error = error)
            null
        }
        // A failed item keeps its .part files only when a retry could continue from them (network errors).
        leftovers?.let { cleanupStaging(it, keepPartial = error.code in RETRYABLE_CODES) }
        return wait
    }

    /** What one yt-dlp run did, for the "run again from the link" decision. */
    private class RunInfo {
        @Volatile var sawProgress = false
        @Volatile var processFailed = false
        @Volatile var errorLog = ""
    }

    /**
     * The probe's info as a private file for `--load-info-json`, or null when it may not or cannot be reused
     * (Off, media link, rate-limited site, signed-in Instagram/TikTok, playlist/tray, no formats, probe too old).
     */
    private fun prepareInfoFile(e: Entry, info: JsonObject?, probedAt: Long): File? {
        if (info == null) return null
        val route = routeOf(e)
        val allowed = lock.withLock { mayReuseProbe(e.url, reuseProbe, route, HashSet(limitedSites), cookiesFile != null) }
        if (!allowed || !infoIsUsable(info, clock() - probedAt)) return null
        return try {
            stagingDir.mkdirs()
            writeInfoJson(File(stagingDir, "tmp"), "item-${e.id}.info.json", info)
        } catch (_: Exception) {
            null // a file that cannot be written just means the download looks the link up again
        }
    }

    /**
     * Runs the download, loading the probe's info when it may be reused. One immediate re-run from the link (not a
     * retry, no backoff, no attempt counted) when that run fails before its first progress line or because the
     * saved lookup went stale (403 / 410 / format not available). The info file is always deleted afterwards.
     * Returns null on success and on a user pause/cancel, and an [ErrorInfo] for a real failure.
     */
    private suspend fun download(e: Entry, info: JsonObject?, probedAt: Long): ErrorInfo? {
        val infoFile = prepareInfoFile(e, info, probedAt)
        try {
            val first = RunInfo()
            val error = downloadOnce(e, infoFile, first)
            if (error == null || infoFile == null) return error
            if (!first.processFailed || !shouldRerunFromUrl(error.code, first.errorLog, first.sawProgress)) return error
            val again = lock.withLock {
                if (!running || e.state !in DOWNLOADING_STATES) {
                    false
                } else {
                    if (e.state != "downloading") setState(e, "downloading")
                    resetProgress(e)
                    true
                }
            }
            if (!again) return error
            infoFile.delete()
            return downloadOnce(e, null, RunInfo())
        } finally {
            infoFile?.delete()
        }
    }

    /** One yt-dlp run ([infoFile] loaded, or the link when null). Same return contract as [download]. */
    private suspend fun downloadOnce(e: Entry, infoFile: File?, run: RunInfo): ErrorInfo? {
        val token = Any()
        val cookies = activeCookiesFile()
        val request = lock.withLock {
            e.token = token
            e.smoother = SpeedSmoother()
            DownloadRequest(
                url = e.url,
                formatSelector = e.formatSelector ?: formatSelector,
                extraArgs = e.extraArgs ?: extraArgs,
                limitRate = limitRate,
                archiveFile = archive.file,
                stagingDir = stagingDir,
                processId = "item-${e.id}",
                expectedBytes = e.expectedBytes,
                cookiesFile = cookies,
                infoJson = infoFile,
            )
        }
        val outcome: DownloadOutcome = try {
            stagingDir.mkdirs()
            val handle = backend.start(request) { progress ->
                run.sawProgress = true
                onProgress(e, token, progress)
            }
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
        } catch (x: Exception) {
            lock.withLock {
                e.handle = null
                e.token = null
                if (e.state == "paused" || e.state == "cancelled") return null
            }
            return withCause(UNKNOWN, sanitizeCause(x))
        }

        // 0 = carry on, 1 = leave it (paused, or already re-queued by a quick resume), 2 = cancelled.
        var ref: StageRef? = null
        val verdict = lock.withLock {
            e.handle = null
            e.token = null
            ref = stageRef(e)
            when {
                e.state == "cancelled" -> 2
                e.state == "paused" -> 1
                // Only DownloadHandle.cancel() sets `terminated`. If the item is back to queued it was resumed
                // before this worker woke: the old process is dead, so this worker steps aside and the scheduler
                // starts a fresh attempt. (Terminated in any other state is a real failure and falls through.)
                outcome.terminated && e.state == "queued" -> 1
                else -> 0
            }
        }
        if (verdict != 0) {
            // A cancelled item must not leave its finished file or partial files behind; a paused one keeps them.
            if (verdict == 2) ref?.let { cleanupStaging(it, keepPartial = false) }
            return null
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
                ref?.let { cleanupStaging(it, keepPartial = false) }
                return null
            }
            var finalPath: String? = null
            if (reported != null) {
                val staged = File(reported)
                val published = try {
                    outputStore.publish(staged, staged.name)
                } catch (c: CancellationException) {
                    throw c
                } catch (_: StoragePermissionException) {
                    return STORAGE_PERMISSION
                } catch (_: Exception) {
                    null
                }
                if (published == null) return PUBLISH_FAILED
                finalPath = published.location
                // The copy can take many seconds: cancel/pause may have happened meanwhile.
                val cancelledMeanwhile = lock.withLock { e.state == "cancelled" }
                if (cancelledMeanwhile) {
                    try {
                        outputStore.delete(published.location)
                    } catch (_: Exception) {
                    }
                    ref?.let { cleanupStaging(it, keepPartial = false) }
                    return null
                }
            }
            lock.withLock {
                // Still downloading, or paused/re-queued during the copy: the file is saved, so the item is done.
                if (e.state !in TERMINAL_STATES) {
                    e.filePath = finalPath
                    e.percent = 100.0
                    e.error = null
                    setState(e, "done", filePath = finalPath, clearError = true)
                }
            }
            return null
        }
        run.processFailed = true
        run.errorLog = outcome.errorLog
        return withCause(explain(outcome.errorLog, e.url, cookies != null), lastLogLine(outcome.errorLog))
    }

    private fun onProgress(e: Entry, token: Any, p: Progress) {
        lock.withLock {
            // A stale token is a dying process from before a pause; "queued" means a quick resume or a retry wait.
            if (e.token !== token || e.state in TERMINAL_STATES || e.state == "paused" || e.state == "queued") return
            val housekeeping = p.postprocessor != null && p.stage == "downloading"
            if (p.stage in STAGES && e.state != p.stage && !housekeeping) setState(e, p.stage)
            e.stage = p.stage
            if ((p.downloadedBytes != null && p.downloadedBytes != e.downloadedBytes) || (p.percent != null && p.percent != e.percent)) {
                e.quietSince = clock() // moving again: the "Starting" reason timer starts over
            }
            p.downloadedBytes?.let { e.downloadedBytes = it }
            p.totalBytes?.let { e.totalBytes = it }
            var speed = p.speed
            var eta = p.eta
            val smoother = e.smoother
            if (smoother != null && p.stage == "downloading" && !housekeeping && p.downloadedBytes != null) {
                // Steadier numbers: the first 2 s of a file stay as reported, then an EMA of the speed.
                val steady = smoother.update(clock(), p.downloadedBytes, e.totalBytes, p.speed, p.eta)
                speed = steady.speed
                eta = steady.eta
            }
            speed?.let { e.speed = it }
            eta?.let { e.eta = it }
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
