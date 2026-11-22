package com.desolate.elisium.ui

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

// Ported from desktop/elisium_downloader/ui/model.py so both apps word sizes and times the same.

private val UNITS = listOf("B", "KB", "MB", "GB", "TB")
private val UNIT_WORDS = listOf("bytes", "kilobytes", "megabytes", "gigabytes", "terabytes")

private fun scale(value: Double): Pair<Double, Int> {
    var size = value
    var unit = 0
    while (size >= 1024 && unit < UNITS.size - 1) {
        size /= 1024
        unit++
    }
    return size to unit
}

private fun number(size: Double, unit: Int): String =
    if (unit == 0) size.roundToInt().toString() else String.format(Locale.ROOT, "%.1f", size)

/** "12.4 MB"; empty for null or negative. */
fun formatBytes(value: Double?): String {
    if (value == null || value < 0) return ""
    val (size, unit) = scale(value)
    return "${number(size, unit)} ${UNITS[unit]}"
}

fun formatBytes(value: Long?): String = formatBytes(value?.toDouble())

/** "2.1 MB/s"; empty for null or zero. */
fun formatSpeed(value: Double?): String {
    if (value == null || value <= 0) return ""
    return "${formatBytes(value)}/s"
}

/** "2.1 megabytes per second" for a screen reader. */
fun speedWords(value: Double?): String {
    if (value == null || value <= 0) return ""
    val (size, unit) = scale(value)
    return "${number(size, unit)} ${UNIT_WORDS[unit]} per second"
}

private fun split(value: Double): Triple<Int, Int, Int> {
    val total = value.roundToInt()
    val hours = total / 3600
    val rest = total % 3600
    return Triple(hours, rest / 60, rest % 60)
}

/** "40s", "2m 5s", "1h 3m"; empty for null or negative. */
fun formatEta(value: Double?): String {
    if (value == null || value < 0) return ""
    val (h, m, s) = split(value)
    return when {
        h > 0 -> if (m > 0) "${h}h ${m}m" else "${h}h"
        m > 0 -> if (s > 0) "${m}m ${s}s" else "${m}m"
        else -> "${s}s"
    }
}

private fun plural(count: Int, word: String) = if (count == 1) "$count $word" else "$count ${word}s"

/** "2 minutes 5 seconds left" for a screen reader; empty for null or negative. */
fun etaWords(value: Double?): String {
    if (value == null || value < 0) return ""
    val (h, m, s) = split(value)
    val parts = buildList {
        if (h > 0) add(plural(h, "hour"))
        if (m > 0) add(plural(m, "minute"))
        if ((s > 0 || isEmpty()) && h == 0) add(plural(s, "second"))
    }
    return parts.joinToString(" ") + " left"
}

/**
 * The visible detail line: "2.1 MB/s - 12.4 MB of 80 MB - 40s left". Parts that are not known
 * are left out, so a download without a size shows only what it has.
 */
fun progressLine(downloaded: Long?, total: Long?, speed: Double?, eta: Double?): String {
    val size = when {
        downloaded != null && total != null && total > 0 -> "${formatBytes(downloaded)} of ${formatBytes(total)}"
        downloaded != null -> formatBytes(downloaded)
        else -> ""
    }
    val left = formatEta(eta).let { if (it.isEmpty()) "" else "$it left" }
    return listOf(formatSpeed(speed), size, left).filter { it.isNotEmpty() }.joinToString(" - ")
}

/** Time left in the Night shelf style, same as desktop: "7 s", "1 min 37 s", "1 h 5 min"; empty for null or negative. */
fun etaText(value: Double?): String {
    if (value == null || value < 0) return ""
    val (h, m, s) = split(value)
    return when {
        h > 0 -> if (m > 0) "$h h $m min" else "$h h"
        m > 0 -> if (s > 0) "$m min $s s" else "$m min"
        else -> "$s s"
    }
}

private val SITES = listOf(
    "youtube.com" to "YouTube", "youtu.be" to "YouTube", "instagram.com" to "Instagram", "tiktok.com" to "TikTok",
    "vimeo.com" to "Vimeo", "soundcloud.com" to "SoundCloud", "twitter.com" to "X", "x.com" to "X",
    "facebook.com" to "Facebook", "twitch.tv" to "Twitch",
)

/** A short, friendly site name for a link ("YouTube"), else the plain host ("example.com"). Same table as desktop. */
fun siteName(url: String?): String {
    val host = runCatching { java.net.URI(url.orEmpty().trim()).host }.getOrNull()?.lowercase().orEmpty()
    for ((suffix, name) in SITES) if (host == suffix || host.endsWith(".$suffix")) return name
    return host.removePrefix("www.").ifEmpty { url.orEmpty() }
}

/** Host of [url] without "www.", or the URL itself when it has none. */
fun siteOf(url: String): String {
    val host = runCatching { java.net.URI(url.trim()).host }.getOrNull()
    return host?.removePrefix("www.")?.takeIf { it.isNotEmpty() } ?: url
}

/** "14 Nov 2026" from an ISO 8601 instant; the raw text when it cannot be parsed. */
fun formatHistoryDate(iso: String?, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
    if (iso.isNullOrBlank()) return ""
    return try {
        DateTimeFormatter.ofPattern("d MMM yyyy", locale).withZone(zone).format(Instant.parse(iso))
    } catch (_: Exception) {
        iso
    }
}
