package com.desolate.elisium.ui.history

import com.desolate.elisium.engine.HistoryRecord
import com.desolate.elisium.ui.formatHistoryDate
import com.desolate.elisium.ui.siteOf
import java.time.ZoneId
import java.util.Locale

/** Can the finished file still be opened? */
enum class FileStatus {
    /** The file is there. */
    Available,

    /** It was downloaded but is gone now ("File no longer exists"). */
    Missing,

    /** Nothing was saved for this entry (failed, cancelled, still running). */
    None,
}

data class HistoryRowModel(
    val id: Long,
    val title: String,
    val site: String,
    val url: String,
    val state: String,
    val date: String,
    val filePath: String?,
    val fileStatus: FileStatus,
)

/** [fileExists] answers `OutputStore.existsAt`; it is only asked for rows that have a saved file. */
fun HistoryRecord.toRowModel(
    fileExists: (String) -> Boolean,
    zone: ZoneId = ZoneId.systemDefault(),
    locale: Locale = Locale.getDefault(),
): HistoryRowModel {
    val path = filePath?.takeIf { it.isNotBlank() }
    val saved = path != null && (state == "done" || state == "skipped")
    return HistoryRowModel(
        id = id,
        title = title?.takeIf { it.isNotBlank() } ?: url,
        site = siteOf(url),
        url = url,
        state = state,
        date = formatHistoryDate(finishedAt ?: createdAt, zone, locale),
        filePath = path,
        fileStatus = when {
            !saved -> FileStatus.None
            fileExists(path!!) -> FileStatus.Available
            else -> FileStatus.Missing
        },
    )
}

/** MIME type for an ACTION_VIEW of a finished file, from its name; the catch-all type when unknown. */
fun mimeForName(name: String): String = when (name.substringAfterLast('.', "").lowercase()) {
    "mp4", "m4v" -> "video/mp4"
    "mkv" -> "video/x-matroska"
    "webm" -> "video/webm"
    "mov" -> "video/quicktime"
    "mp3" -> "audio/mpeg"
    "m4a" -> "audio/mp4"
    "opus", "ogg" -> "audio/ogg"
    "flac" -> "audio/flac"
    "wav" -> "audio/wav"
    else -> "*/*"
}
