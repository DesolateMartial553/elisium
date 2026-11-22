package com.desolate.elisium.media

import java.io.File
import java.util.Locale
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/*
 * Pure functions behind the song snippet and the photo + song video (port of the desktop `mix.py`
 * pure part). Nothing here runs a process: the argv lists are built and tested, `MediaConverter` runs them.
 */

const val MIN_PHOTO_SECONDS = 2.0
const val MIX_FPS = 30
const val MIX_THREADS = "2"
val PORTRAIT: Pair<Int, Int> = 1080 to 1920
val LANDSCAPE: Pair<Int, Int> = 1920 to 1080

/** What ffprobe (or the post's own JSON) says about one file. */
data class StreamInfo(
    val width: Int? = null,
    val height: Int? = null,
    val duration: Double? = null,
    val hasVideo: Boolean = false,
    val hasAudio: Boolean = false,
) {
    /** True / false for a tall / wide picture, null for a square or unknown one. */
    val portrait: Boolean?
        get() {
            val w = width ?: return null
            val h = height ?: return null
            if (w <= 0 || h <= 0 || w == h) return null
            return h > w
        }
}

/** One picture or clip of the video; [seconds] is how long it is shown. [kind] is IMAGE or VIDEO. */
data class Slide(val file: File, val kind: MediaKind, val seconds: Double)

private fun round3(value: Double): Double = Math.round(value * 1000.0) / 1000.0

/** `%.3f` with a dot, whatever the phone's locale is. */
fun clock(value: Double): String = String.format(Locale.ROOT, "%.3f", value)

/** Seconds for each photo: `song / count`, at least 2 s each; the last photo also holds until the song ends. */
fun photoSeconds(songSeconds: Double, photoCount: Int): List<Double> {
    if (photoCount <= 0) return emptyList()
    val each = maxOf(MIN_PHOTO_SECONDS, songSeconds / photoCount)
    val seconds = MutableList(photoCount) { each }
    seconds[photoCount - 1] = maxOf(each, songSeconds - each * (photoCount - 1))
    return seconds.map(::round3)
}

/** 1080x1920 for a portrait majority (ties and unknowns too), else 1920x1080. */
fun chooseCanvas(infos: List<StreamInfo?>): Pair<Int, Int> {
    val tall = infos.count { it?.portrait == true }
    val wide = infos.count { it?.portrait == false }
    return if (wide > tall) LANDSCAPE else PORTRAIT
}

private fun number(value: kotlinx.serialization.json.JsonElement?): Double? {
    val text = (value as? JsonPrimitive)?.contentOrNull?.trim() ?: return null
    val n = text.toDoubleOrNull() ?: return null
    return n.takeIf { it.isFinite() && it >= 0 }
}

private fun rotationOf(stream: JsonObject): Int {
    val candidates = ArrayList<kotlinx.serialization.json.JsonElement?>()
    candidates.add((stream["tags"] as? JsonObject)?.get("rotate"))
    for (side in (stream["side_data_list"] as? JsonArray).orEmpty()) {
        candidates.add((side as? JsonObject)?.get("rotation"))
    }
    for (c in candidates) {
        val text = (c as? JsonPrimitive)?.contentOrNull?.trim() ?: continue
        val value = text.toDoubleOrNull() ?: continue
        return (Math.abs(value).toInt()) % 360
    }
    return 0
}

/** ffprobe `-print_format json -show_format -show_streams` as [StreamInfo]; null when it is not usable. */
fun parseProbeJson(text: String?): StreamInfo? {
    if (text.isNullOrBlank()) return null
    val root = try {
        kotlinx.serialization.json.Json.parseToJsonElement(text) as? JsonObject
    } catch (_: IllegalArgumentException) {
        null
    } ?: return null
    val streams = (root["streams"] as? JsonArray).orEmpty().filterIsInstance<JsonObject>()
    val video = streams.firstOrNull { (it["codec_type"] as? JsonPrimitive)?.contentOrNull == "video" }
    val hasAudio = streams.any { (it["codec_type"] as? JsonPrimitive)?.contentOrNull == "audio" }
    var width: Int? = null
    var height: Int? = null
    if (video != null) {
        val w = number(video["width"])
        val h = number(video["height"])
        if (w != null && h != null && w > 0 && h > 0) {
            width = w.toInt()
            height = h.toInt()
            if (rotationOf(video) % 180 == 90) {
                width = h.toInt()
                height = w.toInt()
            }
        }
    }
    var duration = number((root["format"] as? JsonObject)?.get("duration"))
    if (duration == null) duration = streams.firstNotNullOfOrNull { number(it["duration"]) }
    return StreamInfo(width, height, duration, video != null, hasAudio)
}

/** `ffmpeg -ss <start> -t <length> -i <song> -c copy <output>`; [reencode] is the retry (AAC 192k). */
fun buildCutCommand(
    ffmpeg: String,
    song: String,
    output: String,
    start: Double,
    length: Double,
    reencode: Boolean = false,
): List<String> {
    val argv = arrayListOf(
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "error",
        "-ss", clock(start), "-t", clock(length), "-i", song,
    )
    if (reencode) argv += listOf("-vn", "-c:a", "aac", "-b:a", "192k") else argv += listOf("-c", "copy")
    argv += listOf("-threads", MIX_THREADS, output)
    return argv
}

/**
 * The argv that turns [slides] + [song] into the mp4. Every picture is scaled to fit [canvas] and padded with
 * black bars (`out_range=tv`, so a JPEG's full-range flag cannot leak into the H.264), all are concatenated;
 * the song is the only audio (a clip's own sound is never mapped) and is padded with silence or cut to the
 * total, so the video is exactly as long as its slides.
 */
fun buildMixCommand(
    ffmpeg: String,
    slides: List<Slide>,
    song: String,
    output: String,
    canvas: Pair<Int, Int> = PORTRAIT,
): List<String> {
    require(slides.isNotEmpty()) { "a mix needs at least one slide" }
    val (width, height) = canvas
    val total = slides.sumOf { it.seconds }
    val argv = arrayListOf(
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "error", "-filter_complex_threads", MIX_THREADS,
    )
    val chains = ArrayList<String>()
    slides.forEachIndexed { index, slide ->
        if (slide.kind == MediaKind.IMAGE) {
            argv += listOf("-loop", "1", "-framerate", MIX_FPS.toString(), "-t", clock(slide.seconds))
        }
        argv += listOf("-i", slide.file.path)
        chains += "[$index:v]scale=$width:$height:force_original_aspect_ratio=decrease:out_range=tv," +
            "pad=$width:$height:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=$MIX_FPS," +
            "format=yuv420p[v$index]"
    }
    val songIndex = slides.size
    argv += listOf("-i", song)
    val inputs = slides.indices.joinToString("") { "[v$it]" }
    chains += "${inputs}concat=n=${slides.size}:v=1:a=0[v]"
    chains += "[$songIndex:a]aresample=44100,apad=whole_dur=${clock(total)}[a]"
    argv += listOf(
        "-filter_complex", chains.joinToString(";"),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", MIX_FPS.toString(),
        "-c:a", "aac", "-b:a", "192k",
        "-t", clock(total),
        "-movflags", "+faststart",
        "-threads", MIX_THREADS,
        "-f", "mp4",
        output,
    )
    return argv
}
