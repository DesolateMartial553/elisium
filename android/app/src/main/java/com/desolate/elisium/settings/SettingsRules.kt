package com.desolate.elisium.settings

import com.desolate.elisium.engine.DEFAULT_CONCURRENCY
import com.desolate.elisium.engine.MAX_CONCURRENCY
import com.desolate.elisium.engine.Presets
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength

/** Which Afterglow theme to show: follow the system, or force Nightfall / Daybreak. */
enum class Appearance(val storedValue: String) {
    System("system"),
    Night("night"),
    Day("day"),
    ;

    companion object {
        /** Unknown or missing stored text falls back to [System]. */
        fun fromStored(value: String?): Appearance = entries.firstOrNull { it.storedValue == value } ?: System
    }
}

/** App settings (port of `ui/settings.py`; wifi-only is Android-only, close-to-tray desktop-only). */
data class Settings(
    val concurrency: Int = DEFAULT_CONCURRENCY,
    /** A yt-dlp `--limit-rate` value such as `2M`, or null for no limit. */
    val speedLimit: String? = null,
    val presetId: String = Presets.DEFAULT_ID,
    val wifiOnly: Boolean = true,
    val notifyOnDone: Boolean = true,
    val appearance: Appearance = Appearance.System,
    val reduceMotion: Boolean = false,
    /** Timestamp of the last yt-dlp auto-update check, in ms since epoch. Default 0 (never checked). */
    val lastYtDlpCheck: Long = 0L,
    /** "Photo posts with a song": photos + song + video (default), photos + song, or photos only. */
    val photoMode: PhotoMode = PhotoMode.PhotosSongVideo,
    /** "Song length": the post's snippet (default) or the full track. */
    val songLength: SongLength = SongLength.Snippet,
)

private val LIMIT_RE = Regex("^\\d+(\\.\\d+)?[KMG]?$")

/** [value] trimmed if it is a valid `--limit-rate` string, else null. */
fun validSpeedLimit(value: String?): String? {
    val trimmed = value?.trim() ?: return null
    if (!LIMIT_RE.matches(trimmed)) return null
    // "0" (or 0.0M) would be stored as a limit of nothing; use a blank field for "no limit".
    val number = trimmed.trimEnd('K', 'M', 'G').toDoubleOrNull() ?: return null
    return if (number > 0.0) trimmed else null
}

fun validConcurrency(value: Int?): Int =
    if (value != null && value in 1..MAX_CONCURRENCY) value else DEFAULT_CONCURRENCY

fun isValidConcurrency(value: Int): Boolean = value in 1..MAX_CONCURRENCY

fun validPresetId(value: String?): String =
    if (value != null && value in Presets.PRESETS) value else Presets.DEFAULT_ID

/** Replaces every invalid field with its default (`Settings.validate`). */
fun Settings.validated(): Settings = copy(
    concurrency = validConcurrency(concurrency),
    speedLimit = validSpeedLimit(speedLimit),
    presetId = validPresetId(presetId),
    lastYtDlpCheck = lastYtDlpCheck.coerceAtLeast(0L),
)