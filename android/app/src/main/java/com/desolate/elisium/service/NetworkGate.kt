package com.desolate.elisium.service

import com.desolate.elisium.engine.DownloadQueue

/**
 * Holds the queue while the network does not suit the user's setting (Wi-Fi only on a
 * metered link) and releases it afterwards.
 *
 * Blocking: running items are paused (the `.part` files stay), the queue stops scheduling, and
 * queued items simply stay `queued`. Allowing: the queue starts again and the items this gate
 * paused are resumed. An item the user paused by hand while blocked would be resumed too.
 */
class NetworkGate(private val queue: DownloadQueue) {
    private val held = LinkedHashSet<Int>()
    private var allowed: Boolean? = null

    /** Items the gate paused and will resume. */
    @get:Synchronized
    val heldCount: Int get() = held.size

    /** Forget the items this gate paused (the user took over with Pause all / Cancel all). */
    @Synchronized
    fun dropHeld() = held.clear()

    @Synchronized
    fun setAllowed(value: Boolean) {
        if (allowed == value) return
        allowed = value
        if (value) {
            queue.start()
            for (id in held) queue.resume(id)
            held.clear()
        } else {
            held.addAll(queue.activeIds())
            queue.stop()
        }
    }
}
