package com.desolate.elisium.engine

import java.math.BigDecimal
import java.math.BigInteger
import java.math.RoundingMode
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/** Pure helpers that turn a yt-dlp `-J` object into UI rows (port of `formats.py`). */

const val KIND_BOTH = "video+audio"
const val KIND_VIDEO = "video"
const val KIND_AUDIO = "audio"
private val KIND_RANK = mapOf(KIND_BOTH to 0, KIND_VIDEO to 1, KIND_AUDIO to 2)
private val AUDIO_EXTS = setOf("m4a", "mp3", "opus", "ogg", "oga", "flac", "wav", "aac", "weba")
private val UNAVAILABLE_TITLES = setOf("[private video]", "[deleted video]", "[unavailable]")
private val UNAVAILABLE_AVAILABILITY = setOf("private", "needs_auth")
private val BAD_ID_CHARS = "+/,()[]\"'".toSet()

data class FormatRow(
    val formatId: String,
    val ext: String,
    val resolution: String,
    val fps: Double?,
    val vcodec: String,
    val acodec: String,
    val bitrate: Double?,
    val sizeBytes: Long?,
    val note: String,
    val kind: String,
    val height: Int? = null,
)

data class VideoSummary(
    val title: String,
    val uploader: String,
    val duration: Int?,
    val thumbnail: String?,
    val webpageUrl: String?,
)

data class PlaylistEntry(
    val index: Int,
    val id: String?,
    val title: String,
    val url: String?,
    val duration: Int?,
    val available: Boolean,
)

// -- JSON helpers mirroring Python's dynamic typing -------------------------

private fun JsonObject.field(name: String): JsonElement? = this[name]

/** Python truthiness of a JSON value. */
private fun truthy(e: JsonElement?): Boolean = when (e) {
    null, JsonNull -> false
    is JsonPrimitive -> when {
        e.isString -> e.content.isNotEmpty()
        e.booleanOrNull != null -> e.booleanOrNull == true
        else -> (e.doubleOrNull ?: 0.0) != 0.0
    }
    is JsonArray -> e.isNotEmpty()
    is JsonObject -> e.isNotEmpty()
}

/** `str(value or "")`. */
private fun strOr(e: JsonElement?): String =
    if (!truthy(e)) "" else (e as? JsonPrimitive)?.content ?: e.toString()

private fun num(e: JsonElement?): Double? {
    if (e !is JsonPrimitive || e.isString || e.booleanOrNull != null) return null
    val d = e.doubleOrNull ?: return null
    return if (d.isNaN()) null else d
}

private fun intOf(e: JsonElement?): Long? = num(e)?.toLong()

private fun codec(e: JsonElement?): String =
    if (e is JsonPrimitive && e.isString && e.content.pyStrip().isNotEmpty()) e.content.pyStrip() else ""

private fun text(e: JsonElement?): String =
    if (e is JsonPrimitive && e.isString) e.content.pyStrip() else ""

private fun kindOf(fmt: JsonObject): String? {
    val vcodec = codec(fmt.field("vcodec"))
    val acodec = codec(fmt.field("acodec"))
    var hasVideo = vcodec != "none"
    var hasAudio = acodec != "none"
    if (vcodec.isEmpty() && acodec.isEmpty()) {
        if (truthy(fmt.field("height")) || truthy(fmt.field("width"))) return KIND_BOTH
        if (strOr(fmt.field("ext")).lowercase() in AUDIO_EXTS) return KIND_AUDIO
        return KIND_BOTH
    }
    if (vcodec.isEmpty()) hasVideo = truthy(fmt.field("height")) || truthy(fmt.field("width"))
    if (acodec.isEmpty()) hasAudio = vcodec == "none"
    return when {
        hasVideo && hasAudio -> KIND_BOTH
        hasVideo -> KIND_VIDEO
        hasAudio -> KIND_AUDIO
        else -> null
    }
}

private fun isStoryboard(fmt: JsonObject): Boolean {
    val ext = strOr(fmt.field("ext")).lowercase()
    val note = strOr(fmt.field("format_note")).lowercase()
    val protocol = strOr(fmt.field("protocol")).lowercase()
    return ext == "mhtml" || "storyboard" in note || protocol == "mhtml"
}

/**
 * Rows for every downloadable format, best first: video with audio, video only,
 * audio only; inside a group by height, frame rate and bitrate, highest first.
 * Storyboards (`mhtml`) are skipped.
 */
fun formatRows(info: JsonObject): List<FormatRow> {
    val formats = info["formats"] as? JsonArray ?: return emptyList()
    val rows = ArrayList<FormatRow>()
    for (element in formats) {
        val fmt = element as? JsonObject ?: continue
        if (isStoryboard(fmt)) continue
        val idElement = fmt.field("format_id")
        if (idElement == null || idElement == JsonNull) continue
        val formatId = (idElement as? JsonPrimitive)?.content ?: idElement.toString()
        if (formatId.pyStrip().isEmpty()) continue
        val kind = kindOf(fmt) ?: continue
        val height = intOf(fmt.field("height"))?.toInt()
        val width = intOf(fmt.field("width"))?.toInt()
        val resolution = when {
            kind == KIND_AUDIO -> "audio only"
            width != null && width != 0 && height != null && height != 0 -> "${width}x$height"
            height != null && height != 0 -> "${height}p"
            else -> "unknown"
        }
        var bitrate = num(fmt.field("tbr"))
        if (bitrate == null) {
            val vbr = num(fmt.field("vbr"))
            val abr = num(fmt.field("abr"))
            if (vbr != null || abr != null) bitrate = (vbr ?: 0.0) + (abr ?: 0.0)
        }
        val size = intOf(fmt.field("filesize")) ?: intOf(fmt.field("filesize_approx"))
        val noteElement = if (truthy(fmt.field("format_note"))) fmt.field("format_note") else fmt.field("format")
        rows.add(
            FormatRow(
                formatId = formatId.pyStrip(),
                ext = strOr(fmt.field("ext")),
                resolution = resolution,
                fps = num(fmt.field("fps")),
                vcodec = codec(fmt.field("vcodec")).ifEmpty { if (kind == KIND_AUDIO) "none" else "" },
                acodec = codec(fmt.field("acodec")).ifEmpty { if (kind == KIND_VIDEO) "none" else "" },
                bitrate = bitrate,
                sizeBytes = size,
                note = strOr(noteElement),
                kind = kind,
                height = height,
            ),
        )
    }
    return rows.sortedWith(
        compareBy<FormatRow> { KIND_RANK.getValue(it.kind) }
            .thenBy { -((it.height ?: 0).toLong()) }
            .thenBy { -(it.fps ?: 0.0) }
            .thenBy { -(it.bitrate ?: 0.0) },
    )
}

private fun cleanId(value: String?, what: String): String? {
    if (value == null) return null
    val t = value.pyStrip()
    if (t.isEmpty()) return null
    if (t.any { isPySpace(it) || it in BAD_ID_CHARS }) {
        throw IllegalArgumentException("invalid $what format id: '$value'")
    }
    return t
}

/**
 * The yt-dlp `-f` selector for the chosen formats: `"137+140"`, `"137"` or `"140"`.
 * @throws IllegalArgumentException when both are empty.
 */
fun selectorFor(videoId: String?, audioId: String?): String {
    val video = cleanId(videoId, "video")
    val audio = cleanId(audioId, "audio")
    return when {
        video != null && audio != null -> "$video+$audio"
        video != null -> video
        audio != null -> audio
        else -> throw IllegalArgumentException("choose a video or an audio format")
    }
}

private fun oneDecimal(value: Double): String =
    BigDecimal(value).setScale(1, RoundingMode.HALF_EVEN).toPlainString()

/** `1.5 MB` style size; `unknown` when not known. */
fun humanSize(sizeBytes: Number?): String {
    if (sizeBytes == null || sizeBytes.toDouble() < 0) return "unknown"
    var value = sizeBytes.toDouble()
    for (unit in listOf("B", "KB", "MB", "GB")) {
        if (value < 1024 || unit == "GB") {
            return if (unit == "B") "${value.toLong()} B" else "${oneDecimal(value)} $unit"
        }
        value /= 1024
    }
    return "${oneDecimal(value)} GB"
}

/** `3:05` or `1:02:03`; empty string when not known. */
fun humanDuration(seconds: Number?): String {
    if (seconds == null || seconds.toDouble() < 0) return ""
    val total = Math.rint(seconds.toDouble()).toLong() // Python round(): half to even
    val hours = total / 3600
    val rest = total % 3600
    val minutes = rest / 60
    val secs = rest % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, secs) else "%d:%02d".format(minutes, secs)
}

/** Title, uploader, duration (seconds), thumbnail URL and page URL. */
fun summary(info: JsonObject): VideoSummary {
    var thumbnail: String? = text(info["thumbnail"]).ifEmpty { null }
    if (thumbnail == null) {
        val thumbs = info["thumbnails"] as? JsonArray
        if (thumbs != null) {
            for (thumb in thumbs.reversed()) {
                if (thumb is JsonObject && text(thumb["url"]).isNotEmpty()) {
                    thumbnail = text(thumb["url"])
                    break
                }
            }
        }
    }
    return VideoSummary(
        title = text(info["title"]).ifEmpty { "Untitled video" },
        uploader = text(info["uploader"]).ifEmpty { text(info["channel"]) },
        duration = intOf(info["duration"])?.toInt(),
        thumbnail = thumbnail,
        webpageUrl = text(info["webpage_url"]).ifEmpty { text(info["original_url"]) }.ifEmpty { null },
    )
}

private fun entryUrl(entry: JsonObject): String? {
    for (key in listOf("webpage_url", "url")) {
        val value = text(entry[key])
        if (value.lowercase().startsWith("http://") || value.lowercase().startsWith("https://")) return value
    }
    val videoId = text(entry["id"]).ifEmpty { text(entry["url"]) }
    val ieKey = (if (truthy(entry["ie_key"])) strOr(entry["ie_key"]) else strOr(entry["extractor_key"])).lowercase()
    if (videoId.isNotEmpty() && ieKey.startsWith("youtube") && '/' !in videoId) {
        return "https://www.youtube.com/watch?v=$videoId"
    }
    return null
}

/**
 * One entry per playlist position (1-based), unavailable ones flagged. `null`
 * entries keep their position so a range such as `3-15` matches the playlist's
 * own numbering.
 */
fun playlistEntries(info: JsonObject): List<PlaylistEntry> {
    val entries = info["entries"] as? JsonArray ?: return emptyList()
    val result = ArrayList<PlaylistEntry>()
    entries.forEachIndexed { zero, entry ->
        val position = zero + 1
        if (entry !is JsonObject) {
            result.add(PlaylistEntry(position, null, "Video $position", null, null, false))
            return@forEachIndexed
        }
        val url = entryUrl(entry)
        val title = text(entry["title"]).ifEmpty { text(entry["id"]) }.ifEmpty { url ?: "" }.ifEmpty { "Video $position" }
        val gone = title.lowercase() in UNAVAILABLE_TITLES ||
            strOr(entry["availability"]).lowercase() in UNAVAILABLE_AVAILABILITY
        result.add(
            PlaylistEntry(
                index = position,
                id = text(entry["id"]).ifEmpty { null },
                title = title,
                url = url,
                duration = intOf(entry["duration"])?.toInt(),
                available = url != null && !gone,
            ),
        )
    }
    return result
}

private fun isDigits(s: String) = s.isNotEmpty() && s.all { it in '0'..'9' }

/**
 * Parses `3-15` / `1,4,9-12` into sorted unique 1-based numbers. Blank text gives
 * an empty list. Throws IllegalArgumentException with a plain-language message.
 */
fun parseRange(text: String?, total: Int): List<Int> {
    val cleaned = (text ?: "").pyStrip()
    if (cleaned.isEmpty()) return emptyList()
    val example = "Use numbers like 3-15 or 1,4,9-12."
    val numbers = java.util.TreeSet<Int>()
    for (part in cleaned.replace(" ", "").split(",")) {
        if (part.isEmpty()) throw IllegalArgumentException("There is an extra comma. $example")
        val dash = part.indexOf('-')
        val lowText = if (dash >= 0) part.substring(0, dash) else part
        val highText = if (dash >= 0) part.substring(dash + 1) else ""
        if (!isDigits(lowText) || (dash >= 0 && !isDigits(highText))) {
            throw IllegalArgumentException("\"$part\" is not a number or a range. $example")
        }
        val low = BigInteger(lowText)
        val high = if (dash >= 0) BigInteger(highText) else low
        if (low < BigInteger.ONE || high < BigInteger.ONE) throw IllegalArgumentException("Numbers start at 1.")
        if (low > high) throw IllegalArgumentException("\"$part\" runs backwards; write it as $high-$low.")
        if (high > BigInteger.valueOf(total.toLong())) {
            val noun = if (total == 1) "video" else "videos"
            throw IllegalArgumentException("$high is past the end; this playlist has $total $noun.")
        }
        for (n in low.toInt()..high.toInt()) numbers.add(n)
    }
    return numbers.toList()
}
