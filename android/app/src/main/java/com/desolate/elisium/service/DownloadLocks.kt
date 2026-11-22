package com.desolate.elisium.service

import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.QueueItem

/*
 * Power and Wi-Fi locks that keep a download fast while the screen is off (brief 12D). The decision
 * ("is a download running?") and the acquire/release bookkeeping are plain Kotlin and JVM-tested; the real
 * lock objects (PowerManager.WakeLock, WifiManager.WifiLock) sit behind [HeldLock] in `AndroidHeldLocks.kt`.
 */

/** One lock. [acquire] and [release] must be safe to call in any order and never throw. */
interface HeldLock {
    fun acquire()
    fun release()
}

/** True while at least one item is looking a link up or downloading (probing, downloading, merging, converting). */
fun shouldHoldLocks(items: List<QueueItem>): Boolean = items.any { it.state in ACTIVE_STATES }

/**
 * Holds [locks] while a download runs and lets go as soon as it does not. [update] is called with every
 * queue change; [releaseAll] is called when the service goes idle, errors or is destroyed.
 */
class DownloadLocks(private val locks: List<HeldLock>) {
    private var held = false

    /** True between an acquire and the matching release. */
    @get:Synchronized
    val isHeld: Boolean get() = held

    @Synchronized
    fun update(shouldHold: Boolean) {
        if (shouldHold && !held) {
            held = true
            locks.forEach { runCatching { it.acquire() } }
        } else if (!shouldHold && held) {
            releaseAll()
        }
    }

    @Synchronized
    fun releaseAll() {
        if (!held) return
        held = false
        locks.forEach { runCatching { it.release() } }
    }
}
