package com.desolate.elisium.data

import com.desolate.elisium.engine.TERMINAL_STATES

/** Pure history rules ported from `history.py`, kept apart from Room so the JVM can test them. */
val HISTORY_STATES: Set<String> = setOf(
    "queued", "probing", "downloading", "merging", "converting",
    "paused", "done", "failed", "skipped", "cancelled",
)

fun checkState(state: String): String {
    require(state in HISTORY_STATES) { "unknown state: '$state'" }
    return state
}

/** Escapes `%`, `_` and `\` so a LIKE with `ESCAPE '\'` matches them literally. */
fun escapeLike(text: String): String =
    text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

/** `%text%` with the wildcards inside [text] escaped. */
fun likePattern(text: String): String = "%" + escapeLike(text) + "%"

/** A new row, as `History.add`. [now] is an ISO 8601 UTC string. */
fun newEntity(
    url: String,
    videoKey: String?,
    title: String?,
    state: String,
    errorCode: String?,
    errorMessage: String?,
    filePath: String?,
    now: String,
): HistoryEntity {
    require(url.isNotBlank()) { "url must be a non-empty string" }
    checkState(state)
    return HistoryEntity(
        url = url.trim(),
        videoKey = videoKey,
        title = title,
        state = state,
        errorCode = errorCode,
        errorMessage = errorMessage,
        filePath = filePath,
        createdAt = now,
        finishedAt = if (state in TERMINAL_STATES) now else null,
    )
}

/**
 * `History.update_state`: error code, message and file path are written only when not
 * null; [clearError] resets both error columns; `finished_at` is stamped (once) for a
 * terminal state and cleared when the item becomes active again.
 */
fun applyStateUpdate(
    row: HistoryEntity,
    state: String,
    errorCode: String?,
    errorMessage: String?,
    filePath: String?,
    clearError: Boolean,
    now: String,
): HistoryEntity {
    checkState(state)
    var code = errorCode ?: row.errorCode
    var message = errorMessage ?: row.errorMessage
    if (clearError) {
        code = null
        message = null
    }
    return row.copy(
        state = state,
        errorCode = code,
        errorMessage = message,
        filePath = filePath ?: row.filePath,
        finishedAt = if (state in TERMINAL_STATES) row.finishedAt ?: now else null,
    )
}
