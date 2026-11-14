package com.desolate.elisium.engine

/** Shown on History rows left in an active state when the process died. */
val INTERRUPTED = ErrorInfo("Interrupted when the app closed. Tap Retry.", "Download again", "interrupted")

/**
 * The queue is memory-only, so after a process kill every History row still in a non-final state
 * (queued, probing, downloading, merging, converting, paused) can never finish. Marks each one
 * failed with [INTERRUPTED] so History never shows stuck rows. Run once at app start, before the
 * new queue exists. Returns how many rows were changed; a database error ends the pass quietly.
 */
fun recoverInterrupted(history: HistoryStore, limit: Int = Int.MAX_VALUE): Int {
    var changed = 0
    try {
        for (record in history.recent(limit)) {
            if (record.state in TERMINAL_STATES) continue
            if (history.updateState(record.id, "failed", errorCode = INTERRUPTED.code, errorMessage = INTERRUPTED.message)) changed++
        }
    } catch (_: Exception) {
    }
    return changed
}
