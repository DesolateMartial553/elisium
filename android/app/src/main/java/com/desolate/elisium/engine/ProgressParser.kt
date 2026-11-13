package com.desolate.elisium.engine

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * Pure progress parsing ported from `runner.py` (`stage_for_postprocessor`,
 * `progress_event`, `parse_progress_line`) so the Android backend (brief 5C)
 * and the queue share one stage mapping.
 */
val STAGES: List<String> = listOf("downloading", "merging", "converting")

private val HOUSEKEEPING = setOf("movefiles", "metadata", "ffmpegmetadata", "sponsorblock")
private val ANSI_RE = Regex("\u001b\\[[0-9;?]*[A-Za-z]")
private val KNOWN_KEYS = setOf(
    "downloaded_bytes", "total_bytes", "total_bytes_estimate", "speed", "eta",
    "fragment_index", "postprocessor", "elapsed",
)
private val KNOWN_STATUS = setOf("downloading", "finished", "started", "processing", "error")

/** Maps a yt-dlp post-processor name onto a queue stage. */
fun stageForPostprocessor(name: String?): String {
    val lowered = (name ?: "").lowercase()
    if ("merg" in lowered) return "merging"
    if (lowered in HOUSEKEEPING) return "downloading"
    return "converting"
}

private fun number(e: JsonElement?): Double? {
    if (e !is JsonPrimitive || e.isString || e.booleanOrNull != null) return null
    return e.doubleOrNull
}

private fun roundOne(v: Double): Double = BigDecimal(v).setScale(1, RoundingMode.HALF_EVEN).toDouble()

/** One decoded progress object -> [Progress], or null when it is not a progress report. */
fun progressEvent(data: JsonObject): Progress? {
    val statusEl = data["status"]
    val status = if (statusEl is JsonPrimitive && statusEl.isString) statusEl.content else ""
    if (KNOWN_KEYS.none { it in data } && status !in KNOWN_STATUS) return null

    val downloaded = number(data["downloaded_bytes"])
    val total = number(data["total_bytes"]) ?: number(data["total_bytes_estimate"])
    var percent: Double? = null
    if (downloaded != null && total != null && total != 0.0) {
        percent = roundOne(minOf(downloaded / total, 1.0) * 100.0)
    } else if (status == "finished" && "postprocessor" !in data) {
        percent = 100.0
    }

    if ("postprocessor" in data) {
        val pp = data["postprocessor"]
        val name = if (pp is JsonPrimitive && pp.isString) pp.content else ""
        return Progress(
            stage = stageForPostprocessor(name),
            status = status,
            postprocessor = name.ifEmpty { null },
            percent = percent,
        )
    }
    return Progress(
        stage = "downloading",
        status = status,
        downloadedBytes = downloaded?.toLong(),
        totalBytes = total?.toLong(),
        speed = number(data["speed"]),
        eta = number(data["eta"]),
        percent = percent,
    )
}

/** One output line -> [Progress], or null. Only the JSON object inside the line is used. */
fun parseProgressLine(line: String): Progress? {
    val text = ANSI_RE.replace(line, "").pyStrip()
    val start = text.indexOf('{')
    val end = text.lastIndexOf('}')
    if (start < 0 || end < 0 || end <= start) return null
    val data = try {
        Json.parseToJsonElement(text.substring(start, end + 1))
    } catch (_: Exception) {
        return null
    }
    if (data == JsonNull || data !is JsonObject) return null
    return progressEvent(data)
}
