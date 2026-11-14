package com.desolate.elisium.service

import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.QueueEvent
import com.desolate.elisium.engine.QueueItem
import kotlin.math.roundToInt

/** What the ongoing notification shows. [progressPercent] is set only for a single active item with a known percentage. */
data class NotificationModel(
    val title: String,
    val text: String,
    val progressPercent: Int?,
    val indeterminate: Boolean,
)

const val WAITING_FOR_WIFI = "Waiting for Wi-Fi"

/** True while the service has a reason to stay alive: running or waiting-to-run items, or items held by the network gate. */
fun hasPendingWork(items: List<QueueItem>, heldByNetwork: Int = 0): Boolean =
    items.any { it.state in ACTIVE_STATES || it.state == "queued" } || heldByNetwork > 0

/** "2 downloading, 1 queued" (empty parts are left out). */
fun summaryLine(items: List<QueueItem>): String {
    val downloading = items.count { it.state in ACTIVE_STATES }
    val queued = items.count { it.state == "queued" }
    val parts = buildList {
        if (downloading > 0) add("$downloading downloading")
        if (queued > 0) add("$queued queued")
    }
    return parts.joinToString(", ")
}

private fun stageText(item: QueueItem): String = when (item.state) {
    "merging" -> "Merging"
    "converting" -> "Converting"
    "probing" -> "Preparing"
    else -> "Downloading"
}

/** The ongoing notification for [items]; [holdReason] (e.g. [WAITING_FOR_WIFI]) takes over the title when set. */
fun notificationModel(items: List<QueueItem>, holdReason: String?): NotificationModel {
    val active = items.filter { it.state in ACTIVE_STATES }
    val line = summaryLine(items)
    if (holdReason != null) {
        return NotificationModel(holdReason, line.ifEmpty { "Downloads are on hold" }, null, false)
    }
    if (active.size == 1) {
        val item = active[0]
        val percent = item.percent?.roundToInt()?.coerceIn(0, 100)
        val stage = stageText(item)
        val name = item.title?.takeIf { it.isNotBlank() } ?: item.url
        val queued = items.count { it.state == "queued" }
        val text = buildString {
            append(name)
            if (queued > 0) append(" ($queued queued)")
        }
        val title = if (percent != null && item.state == "downloading") "$stage $percent%" else stage
        return NotificationModel(title, text, percent, percent == null)
    }
    if (active.isEmpty()) {
        return NotificationModel("Elisium", line.ifEmpty { "Waiting for downloads" }, null, false)
    }
    return NotificationModel("Elisium", line, null, true)
}

/** Totals for the downloads that finished since the last completion notification. */
data class BatchSummary(
    val done: Int,
    val failed: Int,
    /** Title of the only finished item, when there is exactly one. */
    val singleTitle: String?,
    /** Plain-language message of the first failure. */
    val firstFailure: String?,
)

/** Collects done/failed transitions from the queue's events. Thread-safe. */
class BatchTracker {
    private var done = 0
    private var failed = 0
    private var singleTitle: String? = null
    private var firstFailure: String? = null

    @Synchronized
    fun onEvent(event: QueueEvent) {
        if (event !is QueueEvent.StateChanged) return
        when (event.state) {
            "done" -> {
                done++
                singleTitle = event.item.title ?: event.item.url
            }
            "failed" -> {
                failed++
                if (firstFailure == null) {
                    val name = event.item.title ?: event.item.url
                    singleTitle = singleTitle ?: name
                    firstFailure = event.item.error?.message ?: "Download failed."
                }
            }
        }
    }

    /** The totals so far, and a reset; null when nothing finished. */
    @Synchronized
    fun take(): BatchSummary? {
        if (done == 0 && failed == 0) return null
        val summary = BatchSummary(done, failed, if (done + failed == 1) singleTitle else null, firstFailure)
        done = 0
        failed = 0
        singleTitle = null
        firstFailure = null
        return summary
    }
}

/** Title and text of the "finished" notification for [summary]. */
fun completionText(summary: BatchSummary): Pair<String, String> = when {
    summary.failed == 0 && summary.done == 1 -> "Download finished" to (summary.singleTitle ?: "")
    summary.failed == 0 -> "${summary.done} downloads finished" to ""
    summary.done == 0 && summary.failed == 1 ->
        "Download failed" to listOfNotNull(summary.singleTitle, summary.firstFailure).joinToString(": ")
    summary.done == 0 -> "${summary.failed} downloads failed" to (summary.firstFailure ?: "")
    else -> "${summary.done} finished, ${summary.failed} failed" to (summary.firstFailure ?: "")
}

/** Should downloads run? Wi-Fi only needs a network that is not metered. */
fun downloadsAllowed(wifiOnly: Boolean, hasNetwork: Boolean, unmetered: Boolean): Boolean =
    !wifiOnly || (hasNetwork && unmetered)
