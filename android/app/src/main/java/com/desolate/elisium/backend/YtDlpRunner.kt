package com.desolate.elisium.backend

import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLException
import com.yausername.youtubedl_android.YoutubeDLRequest

/** What one yt-dlp process produced. */
data class RunResult(
    val exitCode: Int,
    val stdout: String,
    val stderr: String,
    /** The process was destroyed through [YtDlpRunner.destroy] before it finished. */
    val canceled: Boolean = false,
)

/**
 * The one seam between [YoutubeDlBackend] and youtubedl-android, so the backend
 * logic runs on the JVM against a fake.
 */
interface YtDlpRunner {
    /**
     * Runs yt-dlp with [args] then [url], blocking until it exits. [onLine] gets every
     * stdout line (progress templates included). Must not throw for a failing yt-dlp;
     * that is a [RunResult] with a non-zero exit code.
     */
    fun run(args: List<String>, url: String, processId: String, onLine: (String) -> Unit): RunResult

    /** Stops the process registered under [processId]; false if there was none. */
    fun destroy(processId: String): Boolean
}

/**
 * [YtDlpRunner] over youtubedl-android 0.18.1 (`YoutubeDL.execute(request, processId, callback)`).
 * Compile-verified only: it needs the native yt-dlp/python runtime of a real device.
 *
 * The library throws [YoutubeDLException] on a non-zero exit, with only the stderr text as
 * message: the exact exit code and stdout are lost on that path, so the code is reported as 1.
 * It throws `YoutubeDL.CanceledException` when [destroy] removed the process first.
 */
class LibraryYtDlpRunner : YtDlpRunner {
    override fun run(args: List<String>, url: String, processId: String, onLine: (String) -> Unit): RunResult {
        val request = YoutubeDLRequest(url)
        request.addCommands(args)
        return try {
            val response = YoutubeDL.getInstance().execute(request, processId) { _, _, line -> onLine(line) }
            RunResult(response.exitCode, response.out, response.err)
        } catch (e: YoutubeDLException) {
            RunResult(1, "", e.message.orEmpty())
        } catch (_: YoutubeDL.CanceledException) {
            RunResult(-1, "", "", canceled = true)
        } catch (_: InterruptedException) {
            RunResult(-1, "", "", canceled = true)
        }
    }

    override fun destroy(processId: String): Boolean = YoutubeDL.getInstance().destroyProcessById(processId)
}
