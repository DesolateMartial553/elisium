package com.desolate.elisium.media

import java.io.File
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Cancellation shared by everything one media item runs (the HTTP calls, the file downloads, ffmpeg).
 * [cancel] flips the flag and runs the registered closers (`disconnect()`, `Process.destroy()`) so a
 * blocking read or a running ffmpeg stops at once instead of at its next check.
 */
class CancelToken {
    @Volatile
    var cancelled: Boolean = false
        private set
    private val closers = ConcurrentLinkedQueue<() -> Unit>()

    fun cancel() {
        cancelled = true
        while (true) {
            val closer = closers.poll() ?: break
            try {
                closer()
            } catch (_: Exception) {
            }
        }
    }

    /** Registers [closer]; it runs at once when the token is already cancelled. Returns a function that unregisters it. */
    fun onCancel(closer: () -> Unit): () -> Unit {
        closers.add(closer)
        if (cancelled) cancel()
        return { closers.remove(closer) }
    }
}

/** Why a fetch or a file download failed (mapped to plain words in `MediaErrors.kt`). */
enum class MediaFailure { LOGIN_REQUIRED, RATE_LIMITED, NOT_FOUND, PRIVATE, NO_MEDIA, NETWORK, UNKNOWN }

/** [raw] is for the Details log only: never headers, never cookies. */
class MediaFetchException(val failure: MediaFailure, val raw: String = failure.name) : Exception(raw)

/** Looks a post, a story tray or a highlight up and resolves it to downloadable files. */
interface MediaFetcher {
    /** Blocking. [cookiesFile] is the signed-in `cookies.txt` (Instagram only); its contents are never logged. */
    @Throws(MediaFetchException::class)
    fun fetch(url: String, cookiesFile: File?, token: CancelToken): List<MediaPost>
}

/** Saves one file. Blocking; writes `<target>.part` and renames it when complete; stops quietly when [token] is cancelled. */
interface FileDownloader {
    @Throws(MediaFetchException::class)
    fun download(url: String, target: File, token: CancelToken)
}

/**
 * ffmpeg for one item (a fresh session each time, so pause/cancel can stop exactly its process). Run from
 * `nativeLibraryDir/libffmpeg.so` with `LD_LIBRARY_PATH` on a device.
 */
interface FfmpegSession {
    val ffmpegPath: String
    val ffprobePath: String?

    /** True after [terminate] (a pause or cancel). */
    val cancelled: Boolean

    /** Runs [argv] (`argv[0]` is [ffmpegPath]); true on exit code 0. */
    fun run(argv: List<String>, timeoutMs: Long): Boolean

    /** ffprobe's JSON for [file], or null (no ffprobe, failure). */
    fun probeJson(file: File): String?

    fun terminate()
}

/** Everything the queue needs from the media engine; [ffmpeg] gives null when ffmpeg is not there. */
class MediaEngine(
    val fetcher: MediaFetcher,
    val downloader: FileDownloader,
    val ffmpeg: () -> FfmpegSession? = { null },
)
