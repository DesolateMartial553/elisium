package com.desolate.elisium.service

import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.ServiceCompat
import com.desolate.elisium.ElisiumApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Foreground service (type `dataSync`) that keeps the process alive while the queue has work and
 * shows the ongoing "N downloading, M queued" notification with Pause all / Cancel all. It owns no
 * queue state: [DownloadCoordinator] decides when work exists, this service mirrors it and stops
 * itself when [DownloadCoordinator.pending] turns false. Compile-verified only.
 */
class DownloadService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val main = Handler(Looper.getMainLooper())
    private var running = false

    /** Wi-Fi and wake locks, held only while a download runs (released on idle, error and destroy). */
    private lateinit var locks: DownloadLocks

    /** Id of the newest start command; [stopSelfResult] with it never drops a start that arrived later. */
    private var lastStartId = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val app = application as ElisiumApp
        if (!::locks.isInitialized) locks = DownloadLocks(listOf(WifiHeldLock(this), WakeHeldLock(this)))
        lastStartId = startId
        Notifications.ensureChannels(this)
        val coordinator = app.coordinator.value
        val items = coordinator?.queue?.items?.value.orEmpty()
        val first = Notifications.ongoing(this, notificationModel(items, coordinator?.holdReason?.value))
        try {
            ServiceCompat.startForeground(this, ONGOING_ID, first, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException (Android 12+) or a missing type permission.
            coordinator?.reportServiceFailure("Download service could not start: ${e.message}")
            locks.releaseAll()
            stopSelfResult(startId)
            return START_NOT_STICKY
        }
        // pauseAll/cancelAll write History (Room), which refuses the main thread: hand them to the app scope.
        val action = intent?.action
        if (coordinator != null && (action == ACTION_PAUSE_ALL || action == ACTION_CANCEL_ALL)) {
            app.scope.launch {
                if (action == ACTION_PAUSE_ALL) coordinator.pauseAll() else coordinator.cancelAll()
            }
        }
        if (!running) {
            running = true
            scope.launch { follow(app) }
        }
        return START_NOT_STICKY
    }

    private suspend fun follow(app: ElisiumApp) {
        val coordinator = app.coordinator.filterNotNull().first()
        val lockWatch = scope.launch {
            try {
                coordinator.queue.items.collect { locks.update(shouldHoldLocks(it)) }
            } finally {
                locks.releaseAll() // idle, error or cancelled: never keep the radio and CPU awake for nothing
            }
        }
        val updates = scope.launch {
            combine(coordinator.queue.items, coordinator.holdReason) { items, hold -> notificationModel(items, hold) }
                .conflate()
                .collect {
                    Notifications.postOngoing(this@DownloadService, it)
                    delay(NOTIFICATION_INTERVAL_MS)
                }
        }
        coordinator.pending.first { !it }
        updates.cancel()
        lockWatch.cancel()
        locks.releaseAll()
        // New work may have arrived since pending turned false: look again on the main thread before stopping.
        main.post {
            if (coordinator.pending.value) {
                scope.launch { follow(app) }
            } else {
                stopNow(onlyIfNoNewerStart = true)
            }
        }
    }

    /**
     * Leaves the foreground and stops. With [onlyIfNoNewerStart] the stop is skipped when
     * `startForegroundService` delivered another start in the meantime (the service then stays and that
     * start's [onStartCommand] restarts [follow]).
     */
    private fun stopNow(onlyIfNoNewerStart: Boolean = false) {
        running = false
        if (::locks.isInitialized && !onlyIfNoNewerStart) locks.releaseAll()
        if (onlyIfNoNewerStart) {
            // false = a newer start is queued and will call startForeground itself.
            if (stopSelfResult(lastStartId)) stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    /** Android 15 time limit for `dataSync` services: pause everything and stop (the user can resume in the app). */
    override fun onTimeout(startId: Int, fgsType: Int) {
        // Stop first so the Android 15 time limit is always honoured, then pause off the main thread (Room).
        stopNow()
        val app = application as ElisiumApp
        app.scope.launch { app.coordinator.value?.pauseAll() }
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        if (::locks.isInitialized) locks.releaseAll()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_PAUSE_ALL = "com.desolate.elisium.action.PAUSE_ALL"
        const val ACTION_CANCEL_ALL = "com.desolate.elisium.action.CANCEL_ALL"
        private const val NOTIFICATION_INTERVAL_MS = 1000L
    }
}
