package com.desolate.elisium.storage

import java.util.Locale

/** Where finished files go, relative to the shared storage root (with the trailing slash MediaStore uses). */
const val RELATIVE_PATH = "Download/Elisium/"

/** Folder name under the public Downloads directory (API 26-28 path). */
const val FOLDER_NAME = "Elisium"

/**
 * The MediaStore `RELATIVE_PATH` for an owner [subfolder]: `Download/Elisium/<owner>/`. A null, blank or
 * all-dots name keeps the flat `Download/Elisium/` (the name is cleaned by `safeFolderName`, so it can never
 * climb out of the folder or add a level).
 */
fun relativePathFor(subfolder: String?): String {
    val clean = com.desolate.elisium.media.safeFolderName(subfolder) ?: return RELATIVE_PATH
    return "$RELATIVE_PATH$clean/"
}

/** The same folder as a path below the public Downloads directory: `Elisium` or `Elisium/<owner>`. */
fun folderPathFor(subfolder: String?): String {
    val clean = com.desolate.elisium.media.safeFolderName(subfolder) ?: return FOLDER_NAME
    return "$FOLDER_NAME/$clean"
}

/** yt-dlp's `%(title).150B` limit on the title part, in UTF-8 bytes. */
const val TITLE_MAX_BYTES = 150

/** Side files yt-dlp leaves while a download is unfinished; they never count as a finished file. */
private val UNFINISHED_SUFFIXES = listOf(".part", ".ytdl", ".temp", ".elisium-tmp")

private val ID_SUFFIX = Regex(" \\[[^\\]]{1,60}\\]$")

private val MIME_BY_EXTENSION = mapOf(
    "mp4" to "video/mp4",
    "m4v" to "video/x-m4v",
    "mkv" to "video/x-matroska",
    "webm" to "video/webm",
    "mov" to "video/quicktime",
    "avi" to "video/x-msvideo",
    "flv" to "video/x-flv",
    "3gp" to "video/3gpp",
    "ts" to "video/mp2t",
    "mp3" to "audio/mpeg",
    "m4a" to "audio/mp4",
    "aac" to "audio/aac",
    "opus" to "audio/opus",
    "ogg" to "audio/ogg",
    "oga" to "audio/ogg",
    "weba" to "audio/webm",
    "flac" to "audio/flac",
    "wav" to "audio/x-wav",
    "jpg" to "image/jpeg",
    "jpeg" to "image/jpeg",
    "png" to "image/png",
    "webp" to "image/webp",
    "vtt" to "text/vtt",
    "srt" to "application/x-subrip",
    "json" to "application/json",
)

/** What to do with a finished file, given whether a same-named one is already published. */
enum class PublishDecision { INSERT, USE_EXISTING }

fun decidePublish(sameNameExists: Boolean): PublishDecision =
    if (sameNameExists) PublishDecision.USE_EXISTING else PublishDecision.INSERT

/** The MIME type for [fileName] from its extension; unknown extensions are `application/octet-stream`. */
fun mimeTypeFor(fileName: String): String {
    val dot = fileName.lastIndexOf('.')
    if (dot < 0 || dot == fileName.length - 1) return "application/octet-stream"
    return MIME_BY_EXTENSION[fileName.substring(dot + 1).lowercase(Locale.ROOT)] ?: "application/octet-stream"
}

private fun utf8Length(text: String): Int {
    var bytes = 0
    var i = 0
    while (i < text.length) {
        val cp = text.codePointAt(i)
        bytes += when {
            cp < 0x80 -> 1
            cp < 0x800 -> 2
            cp < 0x10000 -> 3
            else -> 4
        }
        i += Character.charCount(cp)
    }
    return bytes
}

/** [text] cut to at most [maxBytes] UTF-8 bytes without splitting a character. */
fun truncateUtf8(text: String, maxBytes: Int): String {
    if (utf8Length(text) <= maxBytes) return text
    var bytes = 0
    var i = 0
    while (i < text.length) {
        val cp = text.codePointAt(i)
        val size = when {
            cp < 0x80 -> 1
            cp < 0x800 -> 2
            cp < 0x10000 -> 3
            else -> 4
        }
        if (bytes + size > maxBytes) break
        bytes += size
        i += Character.charCount(cp)
    }
    return text.substring(0, i)
}

/**
 * A display name safe to hand to MediaStore: `/`, `\`, `:` and control characters removed,
 * leading dots and outer whitespace dropped, and the title part limited to [TITLE_MAX_BYTES]
 * bytes while the ` [id]` suffix and the extension are kept (the id is what dedupe looks for).
 * A name made by the yt-dlp template is therefore returned unchanged.
 */
fun safeDisplayName(name: String): String {
    val cleaned = buildString {
        for (ch in name) {
            if (ch == '/' || ch == '\\' || ch == ':') continue
            if (ch.code < 0x20 || ch.code == 0x7f) continue
            append(ch)
        }
    }.trim().trimStart('.').trim()
    if (cleaned.isEmpty()) return "download"

    val dot = cleaned.lastIndexOf('.')
    val hasExt = dot > 0 && cleaned.length - dot - 1 in 1..10 && cleaned.substring(dot + 1).all { it.isLetterOrDigit() }
    val stem = if (hasExt) cleaned.substring(0, dot) else cleaned
    val ext = if (hasExt) cleaned.substring(dot) else ""
    val suffix = ID_SUFFIX.find(stem)?.value.orEmpty()
    val title = stem.removeSuffix(suffix)
    val shortTitle = truncateUtf8(title, TITLE_MAX_BYTES).trimEnd()
    val result = shortTitle + suffix + ext
    return result.ifEmpty { "download" }
}

/** True for yt-dlp's unfinished side files, which never count as a finished download. */
fun isUnfinishedName(displayName: String): Boolean = UNFINISHED_SUFFIXES.any { displayName.endsWith(it) }

/** Does [displayName] belong to the video [videoId] (`... [<id>].ext`) and look finished? */
fun nameHasVideoId(displayName: String, videoId: String): Boolean =
    videoId.isNotEmpty() && "[$videoId]" in displayName && !isUnfinishedName(displayName)

/** Escapes `%`, `_` and `\` for a SQL LIKE with `ESCAPE '\'`. */
fun escapeLike(text: String): String =
    text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

/** LIKE pattern matching any display name that contains `[<id>]`. */
fun likePatternForVideoId(videoId: String): String = "%" + escapeLike("[$videoId]") + "%"
