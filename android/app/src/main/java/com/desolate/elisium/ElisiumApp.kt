package com.desolate.elisium

import android.app.Application
import com.desolate.elisium.backend.LibraryYtDlpRunner
import com.desolate.elisium.backend.LibraryYtDlpUpdater
import com.desolate.elisium.backend.UpdateResult
import com.desolate.elisium.backend.YtDlpUpdateService
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.backend.YoutubeDlBackend
import com.desolate.elisium.data.AppDatabase
import com.desolate.elisium.data.RoomHistoryStore
import com.desolate.elisium.engine.Archive
import com.desolate.elisium.engine.DownloadQueue
import com.desolate.elisium.engine.HistoryStore
import com.desolate.elisium.engine.OutputStore
import com.desolate.elisium.service.DownloadCoordinator
import com.desolate.elisium.service.shareConfirmation
import com.desolate.elisium.settings.CookieJar
import com.desolate.elisium.settings.SettingsRepository
import com.desolate.elisium.storage.MediaStoreOutputStore
import java.io.File
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import com.yausername.aria2c.Aria2c
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import android.util.Log
import com.desolate.elisium.engine.ORPHAN_MAX_AGE_MS
import com.desolate.elisium.engine.queueLinks
import com.desolate.elisium.engine.recoverInterrupted
import com.desolate.elisium.engine.sweepOrphans
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** State of the bundled download engine (yt-dlp + ffmpeg + aria2c). */
sealed interface EngineState {
    data object Starting : EngineState
    data class Ready(val ytDlpVersion: String) : EngineState
    data class Failed(val message: String) : EngineState
}

class ElisiumApp : Application() {

    /** Application-wide IO scope: the queue's workers, the coordinator and share intake run here. */
    val scope = CoroutineScope(
        SupervisorJob() + Dispatchers.IO +
            CoroutineExceptionHandler { _, t -> Log.e("Elisium", "uncaught error in the app scope", t) },
    )
    private val _engine = MutableStateFlow<EngineState>(EngineState.Starting)
    val engine: StateFlow<EngineState> = _engine.asStateFlow()

    private val _coordinator = MutableStateFlow<DownloadCoordinator?>(null)

    /** The queue wiring; null until the engine is ready (and forever if it failed). */
    val coordinator: StateFlow<DownloadCoordinator?> = _coordinator.asStateFlow()

    /** The application-scoped download queue, or null while the engine is not ready. */
    val queue: DownloadQueue? get() = _coordinator.value?.queue

    override fun onCreate() {
        super.onCreate()
        scope.launch {
            // The queue is memory-only: rows a killed process left active can never finish, and its staged files are orphans.
            try {
                recoverInterrupted(history)
                sweepOrphans(File(filesDir, "staging"), ORPHAN_MAX_AGE_MS)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w("Elisium", "startup recovery failed", e)
            }
            _engine.value = try {
                YoutubeDL.getInstance().init(this@ElisiumApp)
                FFmpeg.getInstance().init(this@ElisiumApp)
                Aria2c.getInstance().init(this@ElisiumApp)
                val version = YoutubeDL.version(this@ElisiumApp) ?: "unknown"
                _coordinator.value = createCoordinator()
                EngineState.Ready(version)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                // UnsatisfiedLinkError, NoClassDefFoundError and friends are Errors: they must show the
                // "engine failed" state, not kill the app.
                EngineState.Failed(e.message ?: e.javaClass.simpleName)
            }
            if (_engine.value is EngineState.Ready) autoUpdateYtDlp()
        }
    }

    /** One update at a time, shared by the startup check and the Settings button. */
    val ytDlpUpdates: YtDlpUpdateService by lazy {
        YtDlpUpdateService(
            updater = LibraryYtDlpUpdater(this),
            store = settingsRepository,
            onResult = { result ->
                // After an update the shown version must follow; a failure changes nothing.
                if (result is UpdateResult.Updated && _engine.value is EngineState.Ready) {
                    _engine.value = EngineState.Ready(result.version)
                }
            },
        )
    }

    /** True while any download is running or waiting (the queue is null before the engine is ready). */
    fun downloadsActive(): Boolean =
        queue?.items?.value?.any { it.state in ACTIVE_STATES || it.state == "queued" } == true

    /** Startup check: runs once, off the main thread, only when the policy allows; failures stay silent. */
    private suspend fun autoUpdateYtDlp() {
        try {
            val result = ytDlpUpdates.autoUpdateIfDue(onWifi = onUnmeteredNetwork(), downloadsActive = downloadsActive())
            if (result is UpdateResult.Failed) Log.w("Elisium", "yt-dlp auto-update failed: ${result.reason}")
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            Log.w("Elisium", "yt-dlp auto-update skipped: ${e.javaClass.simpleName}")
        }
    }

    /** Same notion of "on Wi-Fi" as the Wi-Fi-only download gate: the active network is not metered. */
    private fun onUnmeteredNetwork(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.activeNetwork?.let { cm.getNetworkCapabilities(it) } ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    /** History over Room; usable before the engine is ready (it only needs the database). */
    val history: HistoryStore by lazy { RoomHistoryStore(AppDatabase.get(this).history()) }

    /** Where finished files live; the History screen asks it whether a file still exists. */
    val outputStore: OutputStore by lazy { MediaStoreOutputStore(this) }

    val settingsRepository: SettingsRepository by lazy { SettingsRepository(this) }

    /** The imported cookies.txt (Settings > Accounts); the queue is given its path before every attempt. */
    val cookieJar: CookieJar by lazy { CookieJar(this) }

    private fun createCoordinator(): DownloadCoordinator {
        val queue = DownloadQueue(
            history = history,
            archive = Archive(File(filesDir, "archive.txt")),
            outputStore = outputStore,
            backend = YoutubeDlBackend(LibraryYtDlpRunner()),
            stagingDir = File(filesDir, "staging"),
            scope = scope,
        )
        queue.setCookiesFile(cookieJar.file)
        val coordinator = DownloadCoordinator(this, queue, settingsRepository, scope)
        coordinator.start()
        return coordinator
    }

    /**
     * Waits for the engine, then queues every link of [urls] with the default preset.
     * Returns the confirmation line for the screen. Safe to call from any thread: the database work
     * runs on [Dispatchers.IO] inside (Room refuses the main thread).
     */
    suspend fun addLinks(urls: List<String>): String {
        if (urls.isEmpty()) return shareConfirmation(0, 0, 0)
        engine.first { it !is EngineState.Starting }
        if (engine.value is EngineState.Failed) return "Could not add links: the engine failed to start"
        val queue = _coordinator.filterNotNull().first().queue
        return withContext(Dispatchers.IO) { queueLinks(queue, urls) }
    }
}
