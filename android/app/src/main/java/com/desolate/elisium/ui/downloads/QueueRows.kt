package com.desolate.elisium.ui.downloads

import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.DOWNLOADING_STATES
import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.ui.etaWords
import com.desolate.elisium.ui.progressLine
import com.desolate.elisium.ui.speedWords
import kotlin.math.roundToInt

enum class RowAction { Pause, Resume, Cancel, Retry, SignIn }

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

/** Everything a queue row shows, derived from a [QueueItem]; plain data so it can be JVM-tested. */
data class QueueRowModel(
    val id: Int,
    val title: String,
    val state: String,
    /** Whole percent 0-100, or null when unknown. */
    val percent: Int?,
    val showProgress: Boolean,
    val indeterminate: Boolean,
    /** "12.4 MB of 80 MB - 2.1 MB/s - 40s left" (may be empty). */
    val details: String,
    val speedSpoken: String,
    val etaSpoken: String,
    val errorMessage: String?,
    val errorFix: String?,
    /** The failure is fixed by importing cookies (Settings > Accounts). */
    val needsSignIn: Boolean,
    val actions: List<RowAction>,
)

fun QueueItem.toRowModel(): QueueRowModel {
    val running = state in DOWNLOADING_STATES
    val pct = when {
        state == "done" -> 100
        percent != null -> percent.roundToInt().coerceIn(0, 100)
        else -> null
    }
    val showBar = running || state == "probing"
    val failedLike = state == "failed" || state == "skipped"
    return QueueRowModel(
        id = id,
        title = title?.takeIf { it.isNotBlank() } ?: url,
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

/** Order the one spoken sentence for a row: title, state, percent, speed, time left, error. */
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
