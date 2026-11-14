package com.desolate.elisium.ui

import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.ErrorInfo
import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.engine.TERMINAL_STATES
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.ui.downloads.Banner
import com.desolate.elisium.ui.downloads.ProgressAnnouncer
import com.desolate.elisium.ui.downloads.RowAction
import com.desolate.elisium.ui.downloads.bannerFor
import com.desolate.elisium.ui.downloads.needsCancelConfirmation
import com.desolate.elisium.ui.downloads.needsSignIn
import com.desolate.elisium.ui.downloads.spokenRow
import com.desolate.elisium.ui.downloads.toRowModel
import com.desolate.elisium.ui.downloads.validActions
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

fun queueItem(
    id: Int = 1,
    state: String = "queued",
    title: String? = null,
    url: String = "https://example.com/v/$id",
    percent: Double? = null,
    downloaded: Long? = null,
    total: Long? = null,
    speed: Double? = null,
    eta: Double? = null,
    error: ErrorInfo? = null,
) = QueueItem(
    id = id, recordId = id.toLong(), url = url, identity = url, videoKey = null, state = state, title = title,
    filePath = null, attempts = 0, error = error, stage = null, downloadedBytes = downloaded, totalBytes = total,
    speed = speed, eta = eta, percent = percent,
)

class QueueUiTest {
    @Test fun actionsPerState() {
        assertEquals(listOf(RowAction.Pause, RowAction.Cancel), validActions("queued"))
        assertEquals(listOf(RowAction.Pause, RowAction.Cancel), validActions("probing"))
        assertEquals(listOf(RowAction.Pause, RowAction.Cancel), validActions("downloading"))
        assertEquals(listOf(RowAction.Pause, RowAction.Cancel), validActions("merging"))
        assertEquals(listOf(RowAction.Pause, RowAction.Cancel), validActions("converting"))
        assertEquals(listOf(RowAction.Resume, RowAction.Cancel), validActions("paused"))
        assertEquals(listOf(RowAction.Retry), validActions("failed"))
        assertEquals(listOf(RowAction.Retry), validActions("cancelled"))
        assertEquals(emptyList<RowAction>(), validActions("done"))
        assertEquals(emptyList<RowAction>(), validActions("skipped"))
    }

    @Test fun terminalStatesNeverOfferCancelOrPause() {
        for (s in TERMINAL_STATES) {
            assertFalse(RowAction.Cancel in validActions(s))
            assertFalse(RowAction.Pause in validActions(s))
        }
    }

    @Test fun cancelConfirmationOnlyForActive() {
        for (s in ACTIVE_STATES) assertTrue(s, needsCancelConfirmation(s))
        assertFalse(needsCancelConfirmation("queued"))
        assertFalse(needsCancelConfirmation("paused"))
    }

    @Test fun downloadingRow() {
        val mb = 1024L * 1024
        val row = queueItem(
            state = "downloading", title = "Clip", percent = 15.5, downloaded = 12 * mb, total = 80 * mb,
            speed = 2.0 * mb, eta = 40.0,
        ).toRowModel()
        assertEquals("Clip", row.title)
        assertEquals(16, row.percent)
        assertTrue(row.showProgress)
        assertFalse(row.indeterminate)
        assertEquals("2.0 MB/s - 12.0 MB of 80.0 MB - 40s left", row.details)
        assertEquals("2.0 megabytes per second", row.speedSpoken)
        assertEquals("40 seconds left", row.etaSpoken)
        assertNull(row.errorMessage)
    }

    @Test fun titleFallsBackToUrlAndBlankCounts() {
        assertEquals("https://example.com/v/1", queueItem(title = null).toRowModel().title)
        assertEquals("https://example.com/v/1", queueItem(title = "  ").toRowModel().title)
    }

    @Test fun noPercentMeansIndeterminate() {
        val row = queueItem(state = "downloading").toRowModel()
        assertTrue(row.showProgress)
        assertTrue(row.indeterminate)
        assertNull(row.percent)
        val probing = queueItem(state = "probing", percent = 50.0).toRowModel()
        assertTrue(probing.showProgress)
        assertTrue(probing.indeterminate)
    }

    @Test fun queuedPausedAndDoneRows() {
        val queued = queueItem(state = "queued").toRowModel()
        assertFalse(queued.showProgress)
        assertEquals("", queued.details)
        val paused = queueItem(state = "paused", percent = 40.0, downloaded = 1024, total = 4096, speed = 5.0, eta = 3.0).toRowModel()
        assertFalse(paused.showProgress)
        assertEquals("1.0 KB of 4.0 KB", paused.details)
        assertEquals(40, paused.percent)
        assertEquals(100, queueItem(state = "done").toRowModel().percent)
    }

    @Test fun failedRowCarriesErrorAndRetry() {
        val row = queueItem(state = "failed", error = ErrorInfo("Network problem.", "Retry (auto-retry already ran)", "network")).toRowModel()
        assertEquals("Network problem.", row.errorMessage)
        assertEquals("Retry (auto-retry already ran)", row.errorFix)
        assertEquals(listOf(RowAction.Retry), row.actions)
        // An error left on a running item is not shown.
        assertNull(queueItem(state = "downloading", error = ErrorInfo("x", "y", "z")).toRowModel().errorMessage)
    }

    @Test fun signInFailuresOfferTheAccountsShortcut() {
        for (code in listOf("sign_in_required", "login_required")) {
            val row = queueItem(state = "failed", error = ErrorInfo("Instagram needs you signed in.", "Import cookies in Settings > Accounts", code))
                .toRowModel()
            assertEquals(listOf(RowAction.Retry, RowAction.SignIn), row.actions)
            assertTrue(row.needsSignIn)
        }
        // Other failures keep just Retry, and a queued item never offers Sign in.
        assertFalse(queueItem(state = "failed", error = ErrorInfo("x", "y", "network")).toRowModel().needsSignIn)
        assertFalse(RowAction.SignIn in validActions("failed"))
        assertFalse(RowAction.SignIn in validActions("downloading", "login_required"))
        assertFalse(RowAction.SignIn in validActions("cancelled", "sign_in_required"))
        assertFalse(needsSignIn("done", "login_required"))
    }

    @Test fun percentIsClamped() {
        assertEquals(100, queueItem(state = "downloading", percent = 130.0).toRowModel().percent)
        assertEquals(0, queueItem(state = "downloading", percent = -3.0).toRowModel().percent)
    }

    @Test fun spokenSentenceOrder() {
        val row = queueItem(state = "downloading", title = "Clip", percent = 50.0, speed = 1024.0, eta = 10.0).toRowModel()
        assertEquals(
            "Clip, Downloading, 50 percent, 1.0 kilobytes per second, 10 seconds left",
            spokenRow(row.title, "Downloading", "50 percent", row, null),
        )
        val failed = queueItem(state = "failed", title = "Clip").toRowModel()
        assertEquals("Clip, Failed, Network problem. Retry", spokenRow("Clip", "Failed", null, failed, "Network problem. Retry"))
        assertEquals("Clip, Waiting in line", spokenRow("Clip", "Waiting in line", null, queueItem(title = "Clip").toRowModel(), null))
    }

    @Test fun banners() {
        assertNull(bannerFor(null, null))
        assertEquals(Banner.WaitingForWifi, bannerFor(WAITING_FOR_WIFI, null))
        assertEquals(Banner.ServiceProblem("no"), bannerFor(null, "no"))
        assertEquals(Banner.ServiceProblem("no"), bannerFor(WAITING_FOR_WIFI, "no"))
        assertNull(bannerFor("something else", null))
    }

    private fun rows(vararg items: QueueItem) = items.map { it.toRowModel() }

    private fun announcer() = ProgressAnnouncer({ it }, { "$it percent" })

    @Test fun announcesStateChangesNotFirstSight() {
        val a = announcer()
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "queued", title = "A"))))
        assertEquals(listOf("A: downloading."), a.update(rows(queueItem(state = "downloading", title = "A", percent = 3.0))))
        assertEquals(listOf("A: done."), a.update(rows(queueItem(state = "done", title = "A"))))
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "done", title = "A"))))
    }

    @Test fun announcesFailureWithItsMessage() {
        val a = announcer()
        a.update(rows(queueItem(state = "downloading", title = "A", percent = 1.0)))
        val said = a.update(rows(queueItem(state = "failed", title = "A", error = ErrorInfo("Network problem.", "f", "network"))))
        assertEquals(listOf("A: failed. Network problem."), said)
    }

    @Test fun percentOnlyAtQuarterSteps() {
        val a = announcer()
        a.update(rows(queueItem(state = "downloading", title = "A", percent = 1.0)))
        val said = ArrayList<String>()
        for (p in 2..100) said += a.update(rows(queueItem(state = "downloading", title = "A", percent = p.toDouble())))
        assertEquals(listOf("A, 25 percent", "A, 50 percent", "A, 75 percent"), said)
    }

    @Test fun percentDoesNotRepeatAfterDipAndForgetsRemovedItems() {
        val a = announcer()
        a.update(rows(queueItem(state = "downloading", title = "A", percent = 30.0)))
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "downloading", title = "A", percent = 31.0))))
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "downloading", title = "A", percent = 20.0))))
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "downloading", title = "A", percent = 26.0))))
        a.update(emptyList())
        // Seen again: treated as new, no message.
        assertEquals(emptyList<String>(), a.update(rows(queueItem(state = "queued", title = "A"))))
    }
}
