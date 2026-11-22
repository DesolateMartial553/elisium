package com.desolate.elisium.service

import android.content.Context
import android.net.wifi.WifiManager
import android.os.PowerManager
import android.util.Log

/** A partial wake lock: the CPU keeps running with the screen off. Safety timeout so a bug can never hold it forever. */
class WakeHeldLock(context: Context) : HeldLock {
    private val lock: PowerManager.WakeLock? = try {
        context.applicationContext.getSystemService(PowerManager::class.java)
            ?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Elisium:downloads")?.apply { setReferenceCounted(false) }
    } catch (e: Exception) {
        Log.w(TAG, "wake lock unavailable", e)
        null
    }

    override fun acquire() {
        try {
            lock?.acquire(MAX_HOLD_MS)
        } catch (e: Exception) {
            Log.w(TAG, "wake lock not acquired", e)
        }
    }

    override fun release() {
        try {
            if (lock?.isHeld == true) lock.release()
        } catch (e: Exception) {
            Log.w(TAG, "wake lock not released", e)
        }
    }

    private companion object {
        const val TAG = "ElisiumLocks"
        const val MAX_HOLD_MS = 6L * 60 * 60 * 1000
    }
}

/**
 * A high-performance Wi-Fi lock: the radio stays awake so a download is not slowed by power saving.
 * `WIFI_MODE_FULL_HIGH_PERF` is deprecated and ignored on recent Android versions; it still helps on older ones.
 */
class WifiHeldLock(context: Context) : HeldLock {
    @Suppress("DEPRECATION")
    private val lock: WifiManager.WifiLock? = try {
        context.applicationContext.getSystemService(WifiManager::class.java)
            ?.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "Elisium:downloads")?.apply { setReferenceCounted(false) }
    } catch (e: Exception) {
        Log.w(TAG, "wifi lock unavailable", e)
        null
    }

    override fun acquire() {
        try {
            lock?.acquire()
        } catch (e: Exception) {
            Log.w(TAG, "wifi lock not acquired", e)
        }
    }

    override fun release() {
        try {
            if (lock?.isHeld == true) lock.release()
        } catch (e: Exception) {
            Log.w(TAG, "wifi lock not released", e)
        }
    }

    private companion object {
        const val TAG = "ElisiumLocks"
    }
}
