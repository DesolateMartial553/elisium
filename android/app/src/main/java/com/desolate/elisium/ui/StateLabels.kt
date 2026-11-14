package com.desolate.elisium.ui

import androidx.annotation.StringRes
import com.desolate.elisium.R

/** Plain-words label for a queue/history state (see core-spec states). Unknown states read as "Queued". */
@StringRes
fun stateLabelRes(state: String): Int = when (state) {
    "queued" -> R.string.state_queued
    "probing" -> R.string.state_probing
    "downloading" -> R.string.state_downloading
    "merging" -> R.string.state_merging
    "converting" -> R.string.state_converting
    "paused" -> R.string.state_paused
    "done" -> R.string.state_done
    "failed" -> R.string.state_failed
    "skipped" -> R.string.state_skipped
    "cancelled" -> R.string.state_cancelled
    else -> R.string.state_queued
}
