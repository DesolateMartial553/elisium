package com.desolate.elisium.engine

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/*
 * Display-only facts from the yt-dlp probe (port of the desktop `_thumbnail_from` / `_format_label_from`).
 * They feed the card's picture and kind line; they never reach history.
 */

private fun text(el: Any?): String? = (el as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

/** `thumbnail`, else the last of `thumbnails`; http(s) links only. */
fun thumbnailFrom(info: JsonObject): String? {
    var found = text(info["thumbnail"])
    if (found == null) {
        val thumbs = info["thumbnails"] as? JsonArray
        found = thumbs?.reversed()?.firstNotNullOfOrNull { text((it as? JsonObject)?.get("url")) }
    }
    if (found == null) return null
    val lower = found.lowercase()
    return if (lower.startsWith("http://") || lower.startsWith("https://")) found else null
}

/** A short label such as `1080p MP4` or `MP3 audio`. */
fun formatLabelFrom(info: JsonObject, extraArgs: List<String>): String? {
    if ("-x" in extraArgs || "--extract-audio" in extraArgs) {
        val at = extraArgs.indexOf("--audio-format") + 1
        val format = if (at > 0 && at < extraArgs.size) extraArgs[at].uppercase() else ""
        return if (format.isNotEmpty()) "$format audio" else "Audio"
    }
    val ext = text(info["ext"])?.uppercase().orEmpty()
    val height = (info["height"] as? JsonPrimitive)?.takeIf { !it.isString }?.contentOrNull?.toIntOrNull()
    val quality = if (height != null && height > 0) "${height}p" else ""
    return listOf(quality, ext).filter { it.isNotEmpty() }.joinToString(" ").ifEmpty { null }
}
