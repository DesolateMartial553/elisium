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

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val app = application as ElisiumApp
        Notifications.ensureChannels(this)
        val coordinator = app.coordinator.value
        val items = coordinator?.queue?.items?.value.orEmpty()
        val first = Notifications.ongoing(this, notificationModel(items, coordinator?.holdReason?.value))
        try {
            ServiceCompat.startForeground(this, ONGOING_ID, first, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException (Android 12+) or a missing type permission.
            coordinator?.reportServiceFailure("Download service could not start: ${e.message}")
            stopSelf()
            return START_NOT_STICKY
        }
        when (intent?.action) {
            ACTION_PAUSE_ALL -> coordinator?.pauseAll()
            ACTION_CANCEL_ALL -> coordinator?.cancelAll()
        }
        if (!running) {
            running = true
            scope.launch { follow(app) }
        }
        return START_NOT_STICKY
    }

    private suspend fun follow(app: ElisiumApp) {
        val coordinator = app.coordinator.filterNotNull().first()
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
        // New work may have arrived since pending turned false: look again on the main thread before stopping.
        main.post {
            if (coordinator.pending.value) {
                scope.launch { follow(app) }
            } else {
                stopNow()
            }
        }
    }

    private fun stopNow() {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /** Android 15 time limit for `dataSync` services: pause everything and stop (the user can resume in the app). */
    override fun onTimeout(startId: Int, fgsType: Int) {
        (application as ElisiumApp).coordinator.value?.pauseAll()
        stopNow()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_PAUSE_ALL = "com.desolate.elisium.action.PAUSE_ALL"
        const val ACTION_CANCEL_ALL = "com.desolate.elisium.action.CANCEL_ALL"
        private const val NOTIFICATION_INTERVAL_MS = 1000L
    }
}
