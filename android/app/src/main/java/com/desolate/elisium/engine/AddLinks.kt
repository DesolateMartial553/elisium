package com.desolate.elisium.engine

import com.desolate.elisium.service.shareConfirmation

/**
 * Queues every link of [urls] and returns the confirmation line ("Added 1 link", "Retrying 1 link ...").
 * Blocking (history writes): callers run it on an IO dispatcher. A link the engine cannot normalise is skipped.
 */
fun queueLinks(queue: DownloadQueue, urls: List<String>): String {
    val before = queue.items.value.associate { it.id to it.state }
    var added = 0
    var already = 0
    var retried = 0
    val counted = HashSet<Int>()
    for (url in urls) {
        try {
            val item = queue.add(url)
            if (!counted.add(item.id)) {
                already++
                continue
            }
            val was = before[item.id]
            when {
                was == null -> added++
                was in RETRY_ON_READD && item.state == "queued" -> retried++
                else -> already++
            }
        } catch (_: IllegalArgumentException) {
            // not a link the engine can normalise: skipped
        } catch (_: Exception) {
            // a database or storage error on one link must not drop the rest
        }
    }
    return shareConfirmation(added, already, urls.size, retried)
}

private val RETRY_ON_READD = setOf("failed", "cancelled", "done", "skipped")
