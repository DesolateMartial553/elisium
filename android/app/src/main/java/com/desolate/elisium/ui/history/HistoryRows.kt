package com.desolate.elisium.ui.history

import com.desolate.elisium.engine.HistoryRecord
import com.desolate.elisium.ui.formatHistoryDate
import com.desolate.elisium.ui.siteName
import com.desolate.elisium.ui.siteOf
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
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
    /** A plain-words line the post's row shows ("Already saved", a song note); null when none. */
    val note: String? = null,
    /** How many files the post had (null for single files and older rows). */
    val filesTotal: Int? = null,
    /** The local day the entry finished (or was created), for the day groups; null when the date cannot be read. */
    val day: LocalDate? = null,
    /** "10:41" in the local zone; empty when unknown. */
    val time: String = "",
    /** "YouTube", "Instagram", else the host: what the site filter lists. */
    val siteLabel: String = "",
) {
    /** A photo post or story tray: Open goes to its folder. */
    val multiFile: Boolean get() = (filesTotal ?: 0) > 1
}

/** [fileExists] answers `OutputStore.existsAt`; it is only asked for rows that have a saved file. */
fun HistoryRecord.toRowModel(
    fileExists: (String) -> Boolean,
    zone: ZoneId = ZoneId.systemDefault(),
    locale: Locale = Locale.getDefault(),
): HistoryRowModel {
    val path = filePath?.takeIf { it.isNotBlank() }
    val saved = path != null && (state == "done" || state == "skipped")
    val moment = (finishedAt ?: createdAt).let { iso -> runCatching { Instant.parse(iso).atZone(zone) }.getOrNull() }
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
        note = note?.takeIf { it.isNotBlank() },
        filesTotal = filesTotal,
        day = moment?.toLocalDate(),
        time = moment?.let { DateTimeFormatter.ofPattern("HH:mm", locale).format(it) } ?: "",
        siteLabel = siteName(url),
    )
}

/** The heading over a day's rows: "Today", "Yesterday", or "Thursday 19 November" (with the year when it is not this year). */
fun dayHeading(day: LocalDate, today: LocalDate, locale: Locale = Locale.getDefault()): String {
    val gap = java.time.temporal.ChronoUnit.DAYS.between(day, today)
    if (gap == 0L) return "Today"
    if (gap == 1L) return "Yesterday"
    val pattern = if (day.year == today.year) "EEEE d MMMM" else "EEEE d MMMM yyyy"
    return DateTimeFormatter.ofPattern(pattern, locale).format(day)
}

/** One day of history: the heading and its rows, newest first. */
data class DayGroup(val heading: String, val rows: List<HistoryRowModel>)

/** Groups [rows] (already newest first) by local day; rows without a readable date go last under "Earlier". */
fun groupByDay(rows: List<HistoryRowModel>, today: LocalDate, locale: Locale = Locale.getDefault()): List<DayGroup> {
    val groups = ArrayList<DayGroup>()
    val dated = rows.filter { it.day != null }
    var current: LocalDate? = null
    var bucket = ArrayList<HistoryRowModel>()
    fun flush() {
        val d = current
        if (d != null && bucket.isNotEmpty()) groups.add(DayGroup(dayHeading(d, today, locale), bucket))
        bucket = ArrayList()
    }
    for (row in dated) {
        if (row.day != current) {
            flush()
            current = row.day
        }
        bucket.add(row)
    }
    flush()
    val undated = rows.filter { it.day == null }
    if (undated.isNotEmpty()) groups.add(DayGroup("Earlier", undated))
    return groups
}

/** The sites in [rows] in first-seen order (what the site filter offers after "All"). */
fun siteOptions(rows: List<HistoryRowModel>): List<String> = rows.map { it.siteLabel }.filter { it.isNotEmpty() }.distinct()

/** Rows of one site; every row for null (All). */
fun filterBySite(rows: List<HistoryRowModel>, site: String?): List<HistoryRowModel> =
    if (site == null) rows else rows.filter { it.siteLabel == site }

/** The confirmation line after "Download again": retried when something was queued again, already saved when nothing was. */
fun requeueLine(existed: Boolean, stateAfter: String): String = when {
    !existed -> "Added 1 link"
    stateAfter in setOf("done", "skipped", "failed", "cancelled") -> "Already downloaded, nothing new to fetch"
    else -> "Retrying 1 link"
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
