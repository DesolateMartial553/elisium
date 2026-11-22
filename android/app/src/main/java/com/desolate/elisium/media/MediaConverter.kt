package com.desolate.elisium.media

import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/*
 * The song snippet and the photo + song video, built in the item's staging folder (port of the desktop
 * `mix.process_staging`). Never fails the item: an ffmpeg problem becomes a note.
 */

const val FULL_SONG_NOTE = "Kept the full song: the post doesn't say which part it plays."
const val TRIM_FAILED_NOTE = "Kept the full song: it couldn't be trimmed."
const val MIX_FAILED_NOTE = "Saved the photos and the song; the video couldn't be made."

private const val CUT_TIMEOUT_MS = 300_000L
private const val MIX_TIMEOUT_MS = 3_600_000L
const val MIX_WORK_FOLDER = ".mix-work"

/** A picture or clip of the post, already downloaded; [width]/[height] come from the post's own JSON when known. */
data class Visual(val file: File, val kind: MediaKind, val width: Int? = null, val height: Int? = null)

class ConvertResult(
    /** The saved song (snippet or whole track) in the staging folder, if any. */
    val song: File? = null,
    /** The built video in the staging folder, if it was made. */
    val video: File? = null,
    val note: String? = null,
    /** A video was wanted (so the file count included it). */
    val attemptedVideo: Boolean = false,
    val cancelled: Boolean = false,
)

/** `(start seconds, length seconds)` of the snippet the post plays, or null when the site did not say. */
fun clipTimes(clip: MusicClip?): Pair<Double, Double>? {
    val start = clip?.startMs ?: return null
    val length = clip.durationMs ?: return null
    if (start < 0 || length <= 0) return null
    return start / 1000.0 to length / 1000.0
}

private fun remove(file: File?) {
    try {
        file?.delete()
    } catch (_: Exception) {
    }
}

private fun moveInto(source: File, target: File): Boolean = try {
    Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
    true
} catch (_: Exception) {
    false
}

/**
 * Cuts the song and builds the video.
 *
 * @param songFull the downloaded whole track (`<base> full [<post>_song].<ext>`), or null when it is already cut.
 * @param visuals the downloaded pictures and clips (any order: they are sorted by slide number).
 * @param session ffmpeg, or null when it is missing (the photos and the whole song are kept, with a note).
 * @param existingMix a video of this post is already in the output folder: it is not built again.
 * @param makeVideo false for "photos and song only"; @param cutSong false for "full song".
 * @param onConvert called once, just before the first ffmpeg run (the queue moves the item to `converting`).
 */
fun convertStaging(
    dir: File,
    post: MediaPost,
    base: String,
    songFull: File?,
    visuals: List<Visual>,
    session: FfmpegSession?,
    existingMix: Boolean,
    onConvert: () -> Unit,
    makeVideo: Boolean,
    cutSong: Boolean,
): ConvertResult {
    val cutPrefix = "$base song [${post.id}_song]."
    val cutAlready = dir.listFiles()?.firstOrNull { it.isFile && it.name.startsWith(cutPrefix) && !it.name.endsWith(".part") }
    val full = songFull?.takeIf { it.isFile }
    var song: File = cutAlready ?: full ?: return ConvertResult()
    val times = if (cutAlready != null || !cutSong) null else clipTimes(post.music)
    val mixFile = File(dir, mixName(base, post))
    val ordered = visuals.sortedWith(compareBy({ slideNumber(it.file.name) }, { it.file.name }))
    val wantsVideo = makeVideo && ordered.isNotEmpty() && !existingMix && !mixFile.isFile
    val notes = ArrayList<String>()

    /** The whole track keeps its place under the final song name when nothing was cut. */
    fun keepFull(): File {
        val target = File(dir, songName(base, post, extensionOf(song.name).ifEmpty { "m4a" }))
        return if (song.name == target.name || moveInto(song, target)) target else song
    }

    if (session == null) {
        if (!cutSong) {
            // the user asked for the whole song: nothing to explain
        } else if (cutAlready == null && times == null) {
            notes.add(FULL_SONG_NOTE)
        } else if (times != null) {
            notes.add(TRIM_FAILED_NOTE)
        }
        if (wantsVideo) notes.add(MIX_FAILED_NOTE)
        if (cutAlready == null) song = keepFull()
        return ConvertResult(song, null, notes.joinToString(" ").ifEmpty { null }, wantsVideo)
    }

    val work = File(dir, MIX_WORK_FOLDER)
    if (!work.isDirectory && !work.mkdirs()) {
        if (wantsVideo) notes.add(MIX_FAILED_NOTE)
        if (cutAlready == null) song = keepFull()
        return ConvertResult(song, null, notes.joinToString(" ").ifEmpty { null }, wantsVideo)
    }
    var converting = false
    fun convert() {
        if (!converting) {
            converting = true
            onConvert()
        }
    }

    var video: File? = null
    try {
        // 1. the snippet
        if (cutAlready == null && cutSong) {
            if (times == null) {
                notes.add(FULL_SONG_NOTE)
            } else {
                convert()
                val snippet = cutSnippet(session, song, work, dir, base, post, times)
                if (session.cancelled) return ConvertResult(song, null, null, wantsVideo, cancelled = true)
                if (snippet == null) {
                    notes.add(TRIM_FAILED_NOTE)
                } else {
                    remove(song)
                    song = snippet
                }
            }
        }
        if (cutAlready == null && song.name.contains(" full [")) song = keepFull()

        // 2. the video
        if (wantsVideo) {
            convert()
            video = buildVideo(session, song, ordered, work, mixFile, times)
            if (session.cancelled) return ConvertResult(song, null, null, wantsVideo, cancelled = true)
            if (video == null) notes.add(MIX_FAILED_NOTE)
        }
    } finally {
        work.listFiles()?.forEach { remove(it) }
        remove(work)
    }
    return ConvertResult(song, video, notes.joinToString(" ").ifEmpty { null }, wantsVideo)
}

private fun cutSnippet(
    session: FfmpegSession,
    song: File,
    work: File,
    dir: File,
    base: String,
    post: MediaPost,
    times: Pair<Double, Double>,
): File? {
    val ext = extensionOf(song.name).ifEmpty { "m4a" }
    for ((outExt, reencode) in listOf(ext to false, "m4a" to true)) {
        val scratch = File(work, "snippet.$outExt")
        remove(scratch)
        val argv = buildCutCommand(session.ffmpegPath, song.path, scratch.path, times.first, times.second, reencode)
        val ok = session.run(argv, CUT_TIMEOUT_MS)
        if (session.cancelled) return null
        if (ok && scratch.isFile && scratch.length() > 0) {
            val final = File(dir, songName(base, post, outExt))
            return if (moveInto(scratch, final)) final else null
        }
        remove(scratch)
    }
    return null
}

private fun buildVideo(
    session: FfmpegSession,
    song: File,
    visuals: List<Visual>,
    work: File,
    target: File,
    times: Pair<Double, Double>?,
): File? {
    val songInfo = parseProbeJson(session.probeJson(song))
    val songSeconds = songInfo?.duration?.takeIf { it > 0 } ?: times?.second ?: return null
    val infos = visuals.map { visual ->
        when {
            visual.kind == MediaKind.IMAGE && visual.width != null && visual.height != null ->
                StreamInfo(visual.width, visual.height, null, true, false)
            else -> parseProbeJson(session.probeJson(visual.file))
        }
    }
    val photos = visuals.count { it.kind == MediaKind.IMAGE }
    val photoTimes = photoSeconds(songSeconds, photos).iterator()
    val slides = ArrayList<Slide>()
    visuals.forEachIndexed { index, visual ->
        if (visual.kind == MediaKind.IMAGE) {
            slides.add(Slide(visual.file, MediaKind.IMAGE, photoTimes.next()))
        } else {
            val length = infos[index]?.duration?.takeIf { it > 0 } ?: return null
            slides.add(Slide(visual.file, MediaKind.VIDEO, length))
        }
    }
    val scratch = File(work, "mix.mp4")
    remove(scratch)
    val argv = buildMixCommand(session.ffmpegPath, slides, song.path, scratch.path, chooseCanvas(infos))
    val ok = session.run(argv, MIX_TIMEOUT_MS)
    if (!ok || !scratch.isFile || scratch.length() == 0L) {
        remove(scratch)
        return null
    }
    return if (moveInto(scratch, target)) target else null
}
