package com.desolate.elisium.backend

import com.desolate.elisium.media.FfmpegSession
import java.io.File
import java.util.concurrent.TimeUnit

private val NULL_SINK: ProcessBuilder.Redirect = ProcessBuilder.Redirect.to(File("/dev/null"))

/**
 * [FfmpegSession] that runs the PIE executables the youtubedl-android ffmpeg module ships
 * (`nativeLibraryDir/libffmpeg.so`, `libffprobe.so`) as a child process, with the library's
 * `LD_LIBRARY_PATH` (brief 10A, part 1.2). Compile-verified only: it needs a device.
 *
 * @param ldLibraryPath `<noBackupFilesDir>/youtubedl-android/packages/{python,ffmpeg,aria2c}/usr/lib` joined with `:`.
 */
class ProcessFfmpegSession(
    override val ffmpegPath: String,
    override val ffprobePath: String?,
    private val ldLibraryPath: String,
) : FfmpegSession {
    @Volatile
    override var cancelled: Boolean = false
        private set

    @Volatile
    private var current: Process? = null

    private fun builder(argv: List<String>): ProcessBuilder =
        ProcessBuilder(argv).apply { environment()["LD_LIBRARY_PATH"] = ldLibraryPath }

    override fun run(argv: List<String>, timeoutMs: Long): Boolean {
        if (cancelled) return false
        val process = try {
            builder(argv).redirectErrorStream(true).redirectOutput(NULL_SINK).start()
        } catch (_: Exception) {
            return false
        }
        current = process
        return try {
            if (cancelled) process.destroyForcibly()
            val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
            if (!finished) process.destroyForcibly()
            finished && process.exitValue() == 0 && !cancelled
        } catch (_: InterruptedException) {
            process.destroyForcibly()
            false
        } finally {
            current = null
        }
    }

    override fun probeJson(file: File): String? {
        val probe = ffprobePath ?: return null
        if (cancelled) return null
        return try {
            val process = builder(
                listOf(probe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", file.path),
            ).redirectErrorStream(false).redirectError(NULL_SINK).start()
            current = process
            val text = process.inputStream.bufferedReader().use { it.readText() }
            val ok = process.waitFor(60, TimeUnit.SECONDS) && process.exitValue() == 0
            if (ok) text else null
        } catch (_: Exception) {
            null
        } finally {
            current = null
        }
    }

    override fun terminate() {
        cancelled = true
        current?.destroyForcibly()
    }

    companion object {
        /** A session when `libffmpeg.so` is really there, else null (the item then saves photos and song only). */
        fun create(nativeLibraryDir: File, packagesDir: File): ProcessFfmpegSession? {
            val ffmpeg = File(nativeLibraryDir, "libffmpeg.so")
            if (!ffmpeg.isFile) return null
            val probe = File(nativeLibraryDir, "libffprobe.so").takeIf { it.isFile }
            val ld = listOf("python", "ffmpeg", "aria2c").joinToString(":") { File(packagesDir, "$it/usr/lib").path }
            return ProcessFfmpegSession(ffmpeg.path, probe?.path, ld)
        }
    }
}
