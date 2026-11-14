package com.desolate.elisium.backend

import com.desolate.elisium.engine.DownloadOutcome
import com.desolate.elisium.engine.DownloadRequest
import java.io.File
import java.net.URLDecoder

/*
 * Pure parts of the yt-dlp backend: argv building, playlist detection and outcome
 * interpretation. Ported from `runner.py` (`build_command`, `_looks_like_playlist`)
 * so the JVM tests can pin the same semantics as the desktop app.
 */

/** Dedupe layer 2: fixed name, so the id is always in the filename. */
const val OUTPUT_TEMPLATE = "%(title).150B [%(id)s].%(ext)s"
const val PROGRESS_TEMPLATE = "download:%(progress)j"
const val POSTPROCESS_TEMPLATE = "postprocess:%(progress)j"
const val RETRIES = 3
const val ARCHIVED_MARKER = "has already been recorded in the archive"

/** `<stagingDir>/tmp`: yt-dlp's temp location (`-P temp:`). */
fun tempDirFor(stagingDir: File): File = File(stagingDir, "tmp")

/** `<stagingDir>/<processId>.path`: where yt-dlp writes the final moved file path. */
fun pathFileFor(stagingDir: File, processId: String): File = File(stagingDir, "$processId.path")

/**
 * The yt-dlp arguments (no executable, no URL) for [request], in the same order as
 * the desktop `build_command`. The URL is passed separately and ends up last.
 */
fun buildDownloadArgs(request: DownloadRequest): List<String> {
    val args = mutableListOf(
        "-P", "home:${request.stagingDir.path}",
        "-P", "temp:${tempDirFor(request.stagingDir).path}",
        "--download-archive", request.archiveFile.path,
        "--no-overwrites",
        "--no-mtime",
        "-o", OUTPUT_TEMPLATE,
        "--continue",
        "--no-playlist",
        "--newline",
        "--progress-template", PROGRESS_TEMPLATE,
        "--progress-template", POSTPROCESS_TEMPLATE,
        "--retries", RETRIES.toString(),
        "--fragment-retries", RETRIES.toString(),
        "-f", request.formatSelector,
        "--print-to-file", "after_move:filepath", pathFileFor(request.stagingDir, request.processId).path,
    )
    if (!request.limitRate.isNullOrEmpty()) {
        args += listOf("--limit-rate", request.limitRate)
    }
    args += request.extraArgs
    return args
}

/** The argv a downloader would run: the arguments followed by the URL. */
fun buildDownloadArgv(request: DownloadRequest): List<String> = buildDownloadArgs(request) + request.url

/** The yt-dlp arguments for a probe (`-J`), without the URL. */
fun buildProbeArgs(url: String): List<String> =
    listOf("-J", "--no-download", if (looksLikePlaylist(url)) "--flat-playlist" else "--no-playlist")

private fun decode(text: String): String = try {
    URLDecoder.decode(text, "UTF-8")
} catch (_: IllegalArgumentException) {
    text
}

/** True when [url] addresses a playlist rather than one video (`_looks_like_playlist`). */
fun looksLikePlaylist(url: String): Boolean {
    var rest = url.trim()
    val hash = rest.indexOf('#')
    if (hash >= 0) rest = rest.substring(0, hash)
    val question = rest.indexOf('?')
    val query = if (question >= 0) rest.substring(question + 1) else ""
    var beforeQuery = if (question >= 0) rest.substring(0, question) else rest
    val schemeEnd = beforeQuery.indexOf("://")
    beforeQuery = if (schemeEnd >= 0) {
        val afterAuthority = beforeQuery.indexOf('/', schemeEnd + 3)
        if (afterAuthority >= 0) beforeQuery.substring(afterAuthority) else ""
    } else {
        beforeQuery
    }
    val segments = beforeQuery.split('/').filter { it.isNotEmpty() }

    val params = HashMap<String, String>()
    for (pair in query.split('&')) {
        if (pair.isEmpty()) continue
        val eq = pair.indexOf('=')
        val key = decode((if (eq >= 0) pair.substring(0, eq) else pair).replace('+', ' '))
        val value = if (eq >= 0) decode(pair.substring(eq + 1).replace('+', ' ')) else ""
        params[key] = value
    }
    if (!params["list"].isNullOrEmpty() && params["v"].isNullOrEmpty()) return true
    return segments.isNotEmpty() && segments[0] == "playlist"
}

/**
 * The last non-blank line of the `--print-to-file` output, or null. A playlist
 * download writes one line per file; the queue tracks a single file per item.
 */
fun parsePathFile(text: String?): String? =
    text?.lineSequence()?.map { it.trim() }?.lastOrNull { it.isNotEmpty() }

/** Builds the [DownloadOutcome] from what the process produced. */
fun interpretOutcome(
    exitCode: Int,
    rawLog: String,
    pathFileText: String?,
    terminated: Boolean,
    errorLog: String = rawLog,
): DownloadOutcome {
    val path = if (exitCode == 0 && !terminated) parsePathFile(pathFileText) else null
    val archived = exitCode == 0 && !terminated && path == null && ARCHIVED_MARKER in rawLog
    return DownloadOutcome(
        exitCode = exitCode,
        rawLog = rawLog,
        filePath = path,
        alreadyArchived = archived,
        terminated = terminated,
        errorLog = errorLog,
    )
}

/**
 * The text error classification may read: all of stderr plus the `ERROR:`/`WARNING:` lines of
 * stdout. Other stdout lines carry the video title (`[download] Destination: <title> [id].mp4`),
 * and a title such as "Connection Lost" must not turn an unrelated failure into a network error.
 */
fun classifiableText(stdout: String, stderr: String): String {
    val tagged = stdout.lineSequence().filter {
        val t = it.trimStart()
        t.startsWith("ERROR:") || t.startsWith("WARNING:")
    }.joinToString("\n")
    return listOf(stderr, tagged).filter { it.isNotBlank() }.joinToString("\n")
}
