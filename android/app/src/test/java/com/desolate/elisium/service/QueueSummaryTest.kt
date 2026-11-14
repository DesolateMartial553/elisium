package com.desolate.elisium.service

import com.desolate.elisium.engine.ErrorInfo
import com.desolate.elisium.engine.QueueEvent
import com.desolate.elisium.engine.QueueItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private fun item(
    id: Int,
    state: String,
    title: String? = "Video $id",
    percent: Double? = null,
    error: ErrorInfo? = null,
) = QueueItem(
    id = id, recordId = id.toLong(), url = "https://x.com/$id", identity = "x:$id", videoKey = null,
    state = state, title = title, filePath = null, attempts = 0, error = error, stage = null,
    downloadedBytes = null, totalBytes = null, speed = null, eta = null, percent = percent,
)

private fun changed(item: QueueItem) = QueueEvent.StateChanged(item.id, item.state, "downloading", item)

class QueueSummaryTest {
    @Test
    fun summaryLineCountsDownloadingAndQueued() {
        val items = listOf(item(1, "downloading"), item(2, "merging"), item(3, "queued"), item(4, "done"), item(5, "paused"))
        assertEquals("2 downloading, 1 queued", summaryLine(items))
    }

    @Test
    fun summaryLineLeavesOutEmptyParts() {
        assertEquals("1 queued", summaryLine(listOf(item(1, "queued"))))
        assertEquals("1 downloading", summaryLine(listOf(item(1, "probing"))))
        assertEquals("", summaryLine(listOf(item(1, "done"))))
    }

    @Test
    fun pendingWorkIsActiveOrQueuedOrHeld() {
        assertTrue(hasPendingWork(listOf(item(1, "downloading"))))
        assertTrue(hasPendingWork(listOf(item(1, "queued"))))
        assertTrue(hasPendingWork(listOf(item(1, "paused")), heldByNetwork = 1))
        assertFalse(hasPendingWork(listOf(item(1, "paused"), item(2, "done"), item(3, "failed"))))
        assertFalse(hasPendingWork(emptyList()))
    }

    @Test
    fun singleActiveItemShowsAProgressBar() {
        val m = notificationModel(listOf(item(1, "downloading", title = "Cats", percent = 41.6)), null)
        assertEquals("Downloading 42%", m.title)
        assertEquals("Cats", m.text)
        assertEquals(42, m.progressPercent)
        assertFalse(m.indeterminate)
    }

    @Test
    fun singleActiveItemWithoutPercentIsIndeterminate() {
        val m = notificationModel(listOf(item(1, "probing", percent = null)), null)
        assertEquals("Preparing", m.title)
        assertNull(m.progressPercent)
        assertTrue(m.indeterminate)
    }

    @Test
    fun singleActiveItemMentionsQueuedOnes() {
        val m = notificationModel(listOf(item(1, "merging", title = "A", percent = 100.0), item(2, "queued")), null)
        assertEquals("A (1 queued)", m.text)
        assertEquals("Merging", m.title)
    }

    @Test
    fun missingTitleFallsBackToTheUrl() {
        val m = notificationModel(listOf(item(1, "downloading", title = null, percent = 5.0)), null)
        assertEquals("https://x.com/1", m.text)
    }

    @Test
    fun severalActiveItemsShowTheSummaryAndNoBar() {
        val m = notificationModel(listOf(item(1, "downloading", percent = 10.0), item(2, "downloading"), item(3, "queued")), null)
        assertEquals("2 downloading, 1 queued", m.text)
        assertNull(m.progressPercent)
        assertTrue(m.indeterminate)
    }

    @Test
    fun holdReasonTakesOverTheTitle() {
        val m = notificationModel(listOf(item(1, "queued"), item(2, "queued")), WAITING_FOR_WIFI)
        assertEquals("Waiting for Wi-Fi", m.title)
        assertEquals("2 queued", m.text)
        assertNull(m.progressPercent)
        assertFalse(m.indeterminate)
    }

    @Test
    fun idleModel() {
        val m = notificationModel(emptyList(), null)
        assertEquals("Elisium", m.title)
        assertEquals("Waiting for downloads", m.text)
    }

    @Test
    fun percentIsClamped() {
        assertEquals(100, notificationModel(listOf(item(1, "downloading", percent = 140.0)), null).progressPercent)
        assertEquals(0, notificationModel(listOf(item(1, "downloading", percent = -3.0)), null).progressPercent)
    }

    // -- batch ----------------------------------------------------------
    @Test
    fun batchCountsDoneAndFailedAndResets() {
        val b = BatchTracker()
        assertNull(b.take())
        b.onEvent(changed(item(1, "done")))
        b.onEvent(changed(item(2, "done")))
        b.onEvent(changed(item(3, "failed", error = ErrorInfo("Network problem.", "Retry", "network"))))
        b.onEvent(changed(item(4, "skipped")))
        b.onEvent(changed(item(5, "cancelled")))
        b.onEvent(QueueEvent.ProgressChanged(1, "downloading", item(1, "downloading")))
        val s = b.take()!!
        assertEquals(2, s.done)
        assertEquals(1, s.failed)
        assertEquals("Network problem.", s.firstFailure)
        assertNull(s.singleTitle)
        assertNull(b.take())
    }

    @Test
    fun singleDownloadKeepsItsTitle() {
        val b = BatchTracker()
        b.onEvent(changed(item(1, "done", title = "Cats")))
        assertEquals("Cats", b.take()!!.singleTitle)
    }

    @Test
    fun completionTexts() {
        assertEquals("Download finished" to "Cats", completionText(BatchSummary(1, 0, "Cats", null)))
        assertEquals("3 downloads finished" to "", completionText(BatchSummary(3, 0, null, null)))
        assertEquals(
            "Download failed" to "Cats: Network problem.",
            completionText(BatchSummary(0, 1, "Cats", "Network problem.")),
        )
        assertEquals("2 downloads failed" to "Download failed.", completionText(BatchSummary(0, 2, null, "Download failed.")))
        assertEquals("2 finished, 1 failed" to "Network problem.", completionText(BatchSummary(2, 1, null, "Network problem.")))
    }

    @Test
    fun failureWithoutAnErrorUsesTheGenericMessage() {
        val b = BatchTracker()
        b.onEvent(changed(item(1, "failed", title = "Cats")))
        assertEquals("Download failed.", b.take()!!.firstFailure)
    }

    // -- wifi rule ------------------------------------------------------
    @Test
    fun wifiOnlyRule() {
        assertTrue(downloadsAllowed(wifiOnly = false, hasNetwork = false, unmetered = false))
        assertTrue(downloadsAllowed(wifiOnly = false, hasNetwork = true, unmetered = false))
        assertTrue(downloadsAllowed(wifiOnly = true, hasNetwork = true, unmetered = true))
        assertFalse(downloadsAllowed(wifiOnly = true, hasNetwork = true, unmetered = false))
        assertFalse(downloadsAllowed(wifiOnly = true, hasNetwork = false, unmetered = false))
    }
}
