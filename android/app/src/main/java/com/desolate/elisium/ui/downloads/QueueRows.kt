package com.desolate.elisium.ui.downloads

import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.DOWNLOADING_STATES
import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.engine.WAIT_NETWORK
import com.desolate.elisium.engine.WAIT_RATE_LIMITED
import com.desolate.elisium.engine.WAIT_SIGNING_IN
import com.desolate.elisium.media.MediaRoute
import com.desolate.elisium.media.routeFor
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.ui.etaText
import com.desolate.elisium.ui.etaWords
import com.desolate.elisium.ui.formatBytes
import com.desolate.elisium.ui.formatSpeed
import com.desolate.elisium.ui.progressLine
import com.desolate.elisium.ui.siteName
import com.desolate.elisium.ui.siteOf
import com.desolate.elisium.ui.speedWords
import kotlin.math.roundToInt

enum class RowAction { Pause, Resume, Cancel, Retry, SignIn }

/** The title a photo post, story tray or slideshow shows until the probe names it (same words as desktop). */
const val LOOKING_UP_TITLE = "Looking up the post..."

/** Errors whose fix is "sign in": the row offers a shortcut to Settings > Accounts. */
val SIGN_IN_CODES: Set<String> = setOf("sign_in_required", "login_required", "session_expired", "http_401")

/** Which buttons a row offers for [state]. Only actions the queue will accept are listed. */
fun validActions(state: String, errorCode: String? = null): List<RowAction> = when (state) {
    "queued", "probing", "downloading", "merging", "converting" -> listOf(RowAction.Pause, RowAction.Cancel)
    "paused" -> listOf(RowAction.Resume, RowAction.Cancel)
    "failed" -> if (errorCode in SIGN_IN_CODES) listOf(RowAction.Retry, RowAction.SignIn) else listOf(RowAction.Retry)
    "cancelled" -> listOf(RowAction.Retry)
    else -> emptyList() // done, skipped
}

/** True when this failure is fixed in Settings > Accounts (a sign-in the site wants). */
fun needsSignIn(state: String, errorCode: String?): Boolean =
    state == "failed" && errorCode in SIGN_IN_CODES

/** Cancelling a running item asks first; a waiting or paused one does not. */
fun needsCancelConfirmation(state: String): Boolean = state in ACTIVE_STATES

/** The filter chips above the list. Same states as the desktop count cards (cancelled and skipped show only in All). */
enum class QueueFilter(val key: String) {
    All("all"), Downloading("downloading"), Waiting("waiting"), Failed("failed"), Done("done"),
}

private val FILTER_STATES: Map<QueueFilter, Set<String>> = mapOf(
    QueueFilter.Downloading to setOf("probing", "downloading", "merging", "converting"),
    QueueFilter.Waiting to setOf("queued", "paused"),
    QueueFilter.Failed to setOf("failed"),
    QueueFilter.Done to setOf("done"),
)

/** The chip a state is counted under; null when it only appears in All. */
fun filterOf(state: String): QueueFilter? = FILTER_STATES.entries.firstOrNull { state in it.value }?.key

/** How many rows each chip shows. Zero stays 0 (never blank). */
fun filterCounts(rows: List<QueueRowModel>): Map<QueueFilter, Int> =
    QueueFilter.entries.associateWith { f -> if (f == QueueFilter.All) rows.size else rows.count { filterOf(it.state) == f } }

fun applyFilter(rows: List<QueueRowModel>, filter: QueueFilter): List<QueueRowModel> =
    if (filter == QueueFilter.All) rows else rows.filter { filterOf(it.state) == filter }

/** The colour family of a state's own words. Colour never carries the state alone: the words always say it. */
enum class Tone { Muted, Faint, Positive, Negative }

/** What the 4dp bar shows: nothing (done, failed, queued), the `hue` fill, or the `faint` paused fill. */
enum class BarKind { None, Hue, Paused }

/** Everything a queue row shows, derived from a [QueueItem]; plain data so it can be JVM-tested. */
data class QueueRowModel(
    val id: Int,
    val title: String,
    val state: String,
    /** Whole percent 0-100, or null when unknown. */
    val percent: Int?,
    val showProgress: Boolean,
    val indeterminate: Boolean,
    /** "2.1 MB/s - 12.4 MB of 80 MB - 40s left" (may be empty). */
    val details: String,
    val speedSpoken: String,
    val etaSpoken: String,
    val errorMessage: String?,
    val errorFix: String?,
    /** The failure is fixed by signing in (Settings > Accounts). */
    val needsSignIn: Boolean,
    val actions: List<RowAction>,
    /** http/https picture of the item; null shows the site-name block. */
    val thumbnail: String? = null,
    val site: String = "",
    /** "YouTube - 1080p MP4 - 648.5 MB" or "Instagram - 6 photos + song - 3 of 7 files", with middle dots. */
    val meta: String = "",
    /** A plain-words line under the meta ("Already saved"); null when none. */
    val note: String? = null,
    /** Big figure: "42%" while running or paused with a known percent, else "". */
    val figure: String = "",
    /** The state word shown instead of a figure (Waiting, Checking, Done, Skipped...), "" when [figure] is shown. */
    val stateWord: String = "",
    /** Small line beside it: "4.2 MB/s - 1 min 37 s left", "Paused - 136.0 MB to go", "Starts next". */
    val side: String = "",
    val tone: Tone = Tone.Muted,
    val bar: BarKind = BarKind.None,
    val filePath: String? = null,
    /** A photo post or story tray: Open goes to its folder. */
    val multiFile: Boolean = false,
    /** "Open - Show in folder" is offered (done with a saved file). */
    val canOpen: Boolean = false,
    /** Queue-clock time the row last moved while it is looking the link up or has no progress yet; null otherwise. */
    val startingSince: Long? = null,
    /** The reason "Starting..." shows once the row was quiet for [STALL_AFTER_MS] ("Signing in"...), or null. */
    val stallReason: String? = null,
)

/** A row that has not moved for this long says why ("Starting... Signing in"). */
const val STALL_AFTER_MS = 10_000L
const val STARTING_WORD = "Starting..."
const val REASON_SIGNING_IN = "Signing in"
const val REASON_WAITING_WIFI = "Waiting for Wi-Fi"
const val REASON_WAITING_NETWORK = "Waiting for the network"
const val REASON_RATE_LIMITED = "Rate limited, waiting"

/** The reason to show beside "Starting...": rate limit first, then the Wi-Fi hold, a network retry, a sign-in. */
fun stallReasonFor(hint: String?, waitingForWifi: Boolean): String? = when {
    hint == WAIT_RATE_LIMITED -> REASON_RATE_LIMITED
    waitingForWifi -> REASON_WAITING_WIFI
    hint == WAIT_NETWORK -> REASON_WAITING_NETWORK
    hint == WAIT_SIGNING_IN -> REASON_SIGNING_IN
    else -> null
}

/**
 * What the small line on the right shows: [base] while the row is moving, or "Starting... <reason>" once a
 * row that is still starting has been quiet for [STALL_AFTER_MS]. Pure, so the screen only supplies the time.
 */
fun stallSide(base: String, startingSince: Long?, reason: String?, nowMs: Long): String {
    if (startingSince == null || nowMs - startingSince < STALL_AFTER_MS) return base
    return if (reason == null) STARTING_WORD else "$STARTING_WORD $reason"
}

fun QueueRowModel.sideAt(nowMs: Long): String = stallSide(side, startingSince, stallReason, nowMs)

private val MIDDLE_DOT = " · "

/** "Site · format · size", or for multi-file posts "Instagram · 6 photos + song · 3 of 7 files". */
fun rowMeta(site: String, formatLabel: String?, filesDone: Int?, filesTotal: Int?, state: String, sizeBytes: Long?): String {
    val parts = ArrayList<String>()
    if (site.isNotEmpty()) parts.add(site)
    formatLabel?.takeIf { it.isNotBlank() }?.let { parts.add(it) }
    if (filesTotal != null && filesTotal > 0) {
        parts.add(if (state == "done" || state == "skipped") "$filesTotal files" else "${filesDone ?: 0} of $filesTotal files")
    } else {
        formatBytes(sizeBytes).takeIf { it.isNotEmpty() }?.let { parts.add(it) }
    }
    return parts.joinToString(MIDDLE_DOT)
}

/**
 * The title: the real one, else "Looking up the post..." for a post link being probed, else (instant card) the
 * link's host such as `youtube.com` while queued or probing, else the link.
 */
fun queueTitle(title: String?, url: String, state: String): String = when {
    !title.isNullOrBlank() -> title
    (state == "queued" || state == "probing") && routeFor(url) != MediaRoute.YTDLP -> LOOKING_UP_TITLE
    state == "queued" || state == "probing" -> siteOf(url)
    else -> url
}

fun QueueItem.toRowModel(holdWifi: Boolean = false): QueueRowModel {
    val running = state in DOWNLOADING_STATES
    val total = filesTotal?.takeIf { it > 0 }
    val pct = when {
        state == "done" -> 100
        percent != null -> percent.roundToInt().coerceIn(0, 100)
        total != null -> (100.0 * (filesDone ?: 0) / total).roundToInt().coerceIn(0, 100)
        else -> null
    }
    val showBar = running || state == "probing"
    val failedLike = state == "failed" || state == "skipped"
    val site = siteName(url)
    val size = totalBytes ?: downloadedBytes
    val figureShown = pct != null && (running || state == "paused")
    val sideBits = listOf(formatSpeed(speed), etaText(eta).let { if (it.isEmpty()) "" else "$it left" }).filter { it.isNotEmpty() }
    val toGo = if (totalBytes != null && downloadedBytes != null && totalBytes > downloadedBytes) formatBytes(totalBytes - downloadedBytes) else ""
    val starting = state == "probing" || (state == "downloading" && sideBits.isEmpty())
    val rateLimitedWait = state == "queued" && waitHint == WAIT_RATE_LIMITED
    val savedPath = filePath?.takeIf { it.isNotBlank() }
    val saved = state == "done" && savedPath != null
    return QueueRowModel(
        id = id,
        title = queueTitle(title, url, state),
        state = state,
        percent = pct,
        showProgress = showBar,
        indeterminate = showBar && (pct == null || state == "probing"),
        details = when {
            running -> progressLine(downloadedBytes, totalBytes, speed, eta)
            state == "paused" -> progressLine(downloadedBytes, totalBytes, null, null)
            else -> ""
        },
        speedSpoken = if (running) speedWords(speed) else "",
        etaSpoken = if (running) etaWords(eta) else "",
        errorMessage = if (failedLike) error?.message else null,
        errorFix = if (failedLike) error?.fix else null,
        needsSignIn = needsSignIn(state, error?.code),
        actions = validActions(state, error?.code),
        thumbnail = thumbnail?.takeIf { it.startsWith("http://") || it.startsWith("https://") },
        site = site,
        meta = rowMeta(site, formatLabel, filesDone, total, state, size),
        note = note?.takeIf { it.isNotBlank() },
        figure = if (figureShown) "$pct%" else "",
        stateWord = when {
            figureShown -> ""
            state == "queued" -> "Waiting"
            state == "probing" -> "Checking"
            state == "paused" -> "Paused"
            state == "done" -> "Done"
            state == "skipped" -> "Skipped"
            state == "cancelled" -> "Cancelled"
            state == "failed" -> ""
            running -> if (state == "merging") "Merging" else if (state == "converting") "Converting" else "Downloading"
            else -> ""
        },
        side = when {
            running -> sideBits.joinToString(MIDDLE_DOT).ifEmpty { if (state == "merging") "Merging" else if (state == "converting") "Converting" else "Starting" }
            state == "paused" -> if (toGo.isNotEmpty()) "Paused$MIDDLE_DOT$toGo to go" else "Paused"
            rateLimitedWait -> REASON_RATE_LIMITED
            state == "queued" && holdWifi -> REASON_WAITING_WIFI
            state == "queued" -> formatBytes(totalBytes).ifEmpty { "Starts next" }
            state == "probing" -> "Looking at the link"
            else -> ""
        },
        tone = when (state) {
            "done" -> Tone.Positive
            "failed" -> Tone.Negative
            "queued", "probing", "skipped", "cancelled" -> Tone.Faint
            else -> Tone.Muted
        },
        bar = when {
            running || state == "probing" -> BarKind.Hue
            state == "paused" && pct != null -> BarKind.Paused
            else -> BarKind.None
        },
        filePath = savedPath,
        multiFile = (filesTotal ?: 0) > 1,
        canOpen = saved,
        startingSince = if (starting) quietSince else null,
        stallReason = stallReasonFor(waitHint, holdWifi && state in ACTIVE_STATES),
    )
}

/** The banner above the queue. */
sealed interface Banner {
    data object WaitingForWifi : Banner
    data class ServiceProblem(val message: String) : Banner
}

/** A service problem outranks the Wi-Fi hold (it is the one the user cannot guess). */
fun bannerFor(holdReason: String?, serviceError: String?): Banner? = when {
    serviceError != null -> Banner.ServiceProblem(serviceError)
    holdReason == WAITING_FOR_WIFI -> Banner.WaitingForWifi
    else -> null
}

/** Order the one spoken sentence for a row: title, state, percent, speed, time left, error, note. */
fun spokenRow(
    title: String,
    stateWord: String,
    percentWord: String?,
    row: QueueRowModel,
    errorLine: String?,
): String = listOfNotNull(
    title,
    stateWord,
    percentWord,
    row.speedSpoken.ifEmpty { null },
    row.etaSpoken.ifEmpty { null },
    errorLine?.ifBlank { null },
    row.note,
).joinToString(", ")

/**
 * Decides what a screen reader should be told about queue changes: a state change always
 * ("title: Done"), and percent only when a 25% step is crossed (never per progress tick).
 */
class ProgressAnnouncer(private val stateLabel: (String) -> String, private val percentLabel: (Int) -> String) {
    private val lastState = HashMap<Int, String>()
    private val lastBucket = HashMap<Int, Int>()

    fun update(rows: List<QueueRowModel>): List<String> {
        val messages = ArrayList<String>()
        val live = rows.mapTo(HashSet()) { it.id }
        lastState.keys.retainAll(live)
        lastBucket.keys.retainAll(live)
        for (row in rows) {
            val bucket = (row.percent ?: 0) / 25
            val before = lastState.put(row.id, row.state)
            if (before == null) {
                lastBucket[row.id] = bucket
                continue // first sighting: nothing changed
            }
            if (before != row.state) {
                lastBucket[row.id] = bucket
                val extra = row.errorMessage?.let { " $it" } ?: ""
                messages.add("${row.title}: ${stateLabel(row.state)}.$extra".trim())
                continue
            }
            if (row.state == "downloading" && row.percent != null) {
                val seen = lastBucket[row.id] ?: 0
                if (bucket > seen) {
                    // Only ever upwards, so a dip and recovery is not announced twice.
                    if (bucket in 1..3) messages.add("${row.title}, ${percentLabel(bucket * 25)}")
                    lastBucket[row.id] = bucket
                }
            }
        }
        return messages
    }
}
