package com.desolate.elisium.media

import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/*
 * File names and folder names for media-engine files (desktop `media.py` format strings):
 *   Instagram  `<owner> <date> <shortcode> [<media id>] <n>.<ext>`
 *   TikTok     `<owner> <id> [<id>_<n>] <n>.<ext>`
 *   song       `<base> song [<post>_song].<ext>`   (the staged whole track is `<base> full [<post>_song].<ext>`)
 *   video      `<base> [<post>_mix].mp4`
 * Every name carries a `[marker]` so the "is it already saved" checks can look for the marker.
 */

val IMAGE_EXTENSIONS: Set<String> = setOf("jpg", "jpeg", "png", "webp", "heic", "avif", "gif")
val VIDEO_EXTENSIONS: Set<String> = setOf("mp4", "mov", "webm", "m4v", "mkv")
val AUDIO_EXTENSIONS: Set<String> = setOf("m4a", "mp3", "aac", "opus", "ogg", "wav", "flac")

private val DATE_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(ZoneOffset.UTC)
private val CONTROL = Regex("[\\u0000-\\u001f\\u007f]")
private val TRAILER = Regex("\\s*\\[[^\\]]*]\\s*\\d*\\s*$")
private val NUMBER = Regex("(\\d+)\\.[^.]+$")
private val LAST_MARKER = Regex("\\[([^\\]]+)](?=[^\\[\\]]*$)")

/**
 * One safe folder name from remote text, or null when nothing is left. Path separators and control
 * characters are replaced, leading and trailing dots dropped (port of `safe_folder_name`).
 */
fun safeFolderName(name: String?): String? {
    if (name == null) return null
    val cleaned = name.replace(CONTROL, "_").replace('/', '_').replace('\\', '_')
        .trim().trim('.').trim().take(100).trimEnd('.', ' ')
    return cleaned.ifEmpty { null }
}

/** `yyyy-MM-dd` (UTC) for an epoch-seconds timestamp, or null. */
fun postDate(takenAt: Long?): String? =
    takenAt?.takeIf { it > 0 }?.let { DATE_FORMAT.format(Instant.ofEpochSecond(it)) }

private fun cleanPart(text: String): String =
    text.replace(CONTROL, "").replace("/", "").replace("\\", "").replace(":", "").replace("[", "(").replace("]", ")").trim()

/** The shared first part of every file name of [post]; [fallbackOwner] is the user named in the link. */
fun postBase(post: MediaPost, fallbackOwner: String? = null): String {
    val owner = cleanPart(post.owner ?: fallbackOwner ?: post.site)
    val parts = if (post.site == MediaSites.TIKTOK) {
        listOf(owner, post.id)
    } else {
        listOf(owner, postDate(post.takenAt), post.id)
    }
    return parts.filterNotNull().filter { it.isNotEmpty() }.joinToString(" ")
}

/** The final name of one picture or clip. */
fun mediaFileName(base: String, item: MediaItem): String =
    "$base [${item.mediaId}] ${item.index}.${item.ext}"

/** The staged whole song, before it is cut or renamed. */
fun fullSongName(base: String, post: MediaPost, ext: String): String = "$base full [${post.id}_song].$ext"

/** The saved song (the snippet, or the whole track when it could not be cut). */
fun songName(base: String, post: MediaPost, ext: String): String = "$base song [${post.id}_song].$ext"

/** The built slideshow video. */
fun mixName(base: String, post: MediaPost): String = "$base [${post.id}_mix].mp4"

/** `<base>` of a song file name: no extension, no ` song`/` full` word, no trailing `[id] n`. */
fun songBase(songFileName: String): String {
    var stem = songFileName.substringBeforeLast('.', songFileName)
    for (word in listOf(" song", " full")) {
        val at = stem.lastIndexOf("$word [")
        if (at >= 0) stem = stem.substring(0, at) + stem.substring(at + word.length)
        else if (stem.endsWith(word)) stem = stem.removeSuffix(word)
    }
    val trimmed = stem.replace(TRAILER, "").trim()
    return trimmed.ifEmpty { stem.ifEmpty { "song" } }
}

/** The trailing slide number of a file name (`... 3.jpg` gives 3), or a large number when absent. */
fun slideNumber(name: String): Int = NUMBER.find(name)?.groupValues?.get(1)?.toIntOrNull() ?: Int.MAX_VALUE

/** The `[marker]` in a finished file name (the last bracket group), or null. */
fun markerOf(fileName: String): String? {
    val stem = fileName.substringBeforeLast('.', fileName)
    return LAST_MARKER.find(stem.trimEnd())?.groupValues?.get(1)
        ?: Regex("\\[([^\\]]+)]").findAll(stem).lastOrNull()?.groupValues?.get(1)
}

fun extensionOf(fileName: String): String = fileName.substringAfterLast('.', "").lowercase()
