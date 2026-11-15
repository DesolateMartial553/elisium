package com.desolate.elisium.backend

import android.content.Context
import android.util.Log
import com.desolate.elisium.settings.SettingsStore
import com.yausername.youtubedl_android.YoutubeDL
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext

/** What one yt-dlp update produces. */
sealed interface UpdateResult {
    data class Updated(val version: String) : UpdateResult
    data class AlreadyUpToDate(val version: String) : UpdateResult
    data class Failed(val reason: String) : UpdateResult
}

/** The one seam between the app and the library's updater. Blocking: call it off the main thread. */
interface YtDlpUpdater {
    fun update(): UpdateResult
}

private const val MAX_REASON_CHARS = 80

/** A short one-line reason for [Throwable]: its message when it has one, else its class name. */
internal fun shortReason(t: Throwable): String {
    val raw = (t.message ?: t.javaClass.simpleName).lineSequence().firstOrNull { it.isNotBlank() }?.trim()
        ?: t.javaClass.simpleName
    return if (raw.length <= MAX_REASON_CHARS) raw else raw.take(MAX_REASON_CHARS - 1) + "…"
}

/** [YtDlpUpdater] backed by youtubedl-android 0.18.1 (`updateYoutubeDL` on the STABLE channel). */
class LibraryYtDlpUpdater(private val context: Context) : YtDlpUpdater {
    override fun update(): UpdateResult = try {
        val status = YoutubeDL.getInstance().updateYoutubeDL(context, YoutubeDL.UpdateChannel.STABLE)
        val version = YoutubeDL.version(context) ?: "unknown"
        when (status) {
            YoutubeDL.UpdateStatus.DONE -> UpdateResult.Updated(version)
            YoutubeDL.UpdateStatus.ALREADY_UP_TO_DATE -> UpdateResult.AlreadyUpToDate(version)
            else -> UpdateResult.Failed("no result from the updater")
        }
    } catch (e: CancellationException) {
        throw e
    } catch (t: Throwable) {
        // No network, GitHub unreachable, library error (even an Error): never crash the app.
        val reason = shortReason(t)
        Log.w("Elisium", "yt-dlp update failed: $reason")
        UpdateResult.Failed(reason)
    }
}

/**
 * Runs one update at a time (the manual button and the startup check share it), off the main
 * thread, and stores the time of every finished attempt, success or failure, so a failing update is
 * not retried on every launch.
 */
class YtDlpUpdateService(
    private val updater: YtDlpUpdater,
    private val store: SettingsStore,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    private val clock: () -> Long = System::currentTimeMillis,
    /** Called after every finished attempt (the app refreshes the shown yt-dlp version here). */
    private val onResult: (UpdateResult) -> Unit = {},
) {
    private val _running = MutableStateFlow(false)

    /** True while an update runs. */
    val running: StateFlow<Boolean> = _running.asStateFlow()

    /** Runs an update now; null when one is already running. */
    suspend fun run(): UpdateResult? {
        if (!_running.compareAndSet(false, true)) return null
        try {
            val result = withContext(io) {
                try {
                    updater.update()
                } catch (e: CancellationException) {
                    throw e
                } catch (t: Throwable) {
                    UpdateResult.Failed(shortReason(t))
                }
            }
            store.setLastYtDlpCheck(clock())
            onResult(result)
            return result
        } finally {
            _running.value = false
        }
    }

    /** Runs an update only when [shouldAutoUpdate] allows it; null when skipped. */
    suspend fun autoUpdateIfDue(onWifi: Boolean, downloadsActive: Boolean): UpdateResult? {
        val s = store.settings.first()
        if (!shouldAutoUpdate(clock(), s.lastYtDlpCheck, s.wifiOnly, onWifi, downloadsActive)) return null
        return run()
    }
}
