package com.desolate.elisium.service

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.util.Log
import androidx.core.content.ContextCompat
import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.DownloadQueue
import com.desolate.elisium.engine.Presets
import com.desolate.elisium.engine.TERMINAL_STATES
import com.desolate.elisium.settings.SettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * App-scoped glue between the queue, the settings, the network and the foreground service.
 * It decides when the service must run ([pending]), applies the settings to the queue,
 * holds downloads while the network does not suit "Wi-Fi only" ([holdReason]), and posts the
 * "finished" notification. The decisions it makes live in tested pure code
 * (`QueueSummary.kt`, `NetworkGate.kt`); this class only wires Android pieces together and is
 * compile-verified only.
 */
class DownloadCoordinator(
    context: Context,
    val queue: DownloadQueue,
    private val settings: SettingsRepository,
    private val scope: CoroutineScope,
) {
    private val appContext = context.applicationContext
    private val gate = NetworkGate(queue)
    private val batch = BatchTracker()
    private val connectivity = appContext.getSystemService(ConnectivityManager::class.java)

    private val _holdReason = MutableStateFlow<String?>(null)

    /** Why queued items are not starting ([WAITING_FOR_WIFI]), or null. */
    val holdReason: StateFlow<String?> = _holdReason.asStateFlow()

    private val _pending = MutableStateFlow(false)

    /** True while there is work the foreground service must keep alive. */
    val pending: StateFlow<Boolean> = _pending.asStateFlow()

    private val _serviceError = MutableStateFlow<String?>(null)

    /** Set when Android refused to start the foreground service (queue still runs while the app lives). */
    val serviceError: StateFlow<String?> = _serviceError.asStateFlow()

    private val netLock = Any()
    private var wifiOnly = true
    private var notifyOnDone = true
    private var hasNetwork = false
    private var unmetered = false
    private var currentNetwork: Network? = null

    fun start() {
        scope.launch(start = CoroutineStart.UNDISPATCHED) { queue.events.collect { batch.onEvent(it) } }
        scope.launch {
            settings.settings.collect { s ->
                queue.concurrency = s.concurrency
                queue.setLimitRate(s.speedLimit)
                val preset = Presets.get(s.presetId)
                queue.setFormatSelector(preset.formatSelector)
                queue.setExtraArgs(preset.extraArgs)
                synchronized(netLock) {
                    wifiOnly = s.wifiOnly
                    notifyOnDone = s.notifyOnDone
                }
                reevaluate()
            }
        }
        scope.launch {
            queue.items.collect { items ->
                val pendingNow = hasPendingWork(items, gate.heldCount)
                val was = _pending.value
                if (pendingNow && !was) {
                    _pending.value = true
                    startService()
                } else if (!pendingNow && was) {
                    _pending.value = false
                    val summary = batch.take()
                    if (summary != null && synchronized(netLock) { notifyOnDone }) {
                        Notifications.ensureChannels(appContext)
                        Notifications.postCompletion(appContext, summary)
                    }
                }
            }
        }
        registerNetwork()
    }

    private fun registerNetwork() {
        val active = connectivity.activeNetwork
        val caps = active?.let { connectivity.getNetworkCapabilities(it) }
        synchronized(netLock) {
            hasNetwork = caps != null
            currentNetwork = if (caps != null) active else null
            unmetered = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true
        }
        reevaluate()
        connectivity.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                synchronized(netLock) {
                    hasNetwork = true
                    currentNetwork = network
                }
                reevaluate()
            }

            override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
                synchronized(netLock) {
                    hasNetwork = true
                    currentNetwork = network
                    unmetered = networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
                }
                reevaluate()
            }

            override fun onLost(network: Network) {
                synchronized(netLock) {
                    // A late "lost" for the previous network must not hide the one we already switched to.
                    if (currentNetwork != null && currentNetwork != network) return
                    hasNetwork = false
                    unmetered = false
                    currentNetwork = null
                }
                reevaluate()
            }
        })
    }

    private fun reevaluate() {
        val allowed = synchronized(netLock) { downloadsAllowed(wifiOnly, hasNetwork, unmetered) }
        _holdReason.value = if (allowed) null else WAITING_FOR_WIFI
        gate.setAllowed(allowed)
    }

    /** Pauses everything running or waiting (the notification's "Pause all"). */
    fun pauseAll() {
        gate.dropHeld()
        for (item in queue.items.value) {
            if (item.state in ACTIVE_STATES || item.state == "queued") queue.pause(item.id)
        }
    }

    /** Cancels every unfinished item (the notification's "Cancel all"). */
    fun cancelAll() {
        gate.dropHeld()
        for (item in queue.items.value) {
            if (item.state !in TERMINAL_STATES) queue.cancel(item.id)
        }
    }

    private fun startService() {
        try {
            ContextCompat.startForegroundService(appContext, Intent(appContext, DownloadService::class.java))
            _serviceError.value = null
        } catch (e: IllegalStateException) {
            // Android 12+: ForegroundServiceStartNotAllowedException when the app is in the background.
            _serviceError.value = "Android would not start the download service: ${e.message}"
            Log.w(TAG, "foreground service start refused", e)
        } catch (e: SecurityException) {
            _serviceError.value = "Missing permission for the download service: ${e.message}"
            Log.w(TAG, "foreground service start not permitted", e)
        }
    }

    /** Called by the service when it could not enter the foreground. */
    fun reportServiceFailure(message: String) {
        _serviceError.value = message
    }

    private companion object {
        const val TAG = "ElisiumCoordinator"
    }
}
