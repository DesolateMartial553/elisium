package com.desolate.elisium.ui

import com.desolate.elisium.engine.WAIT_NETWORK
import com.desolate.elisium.engine.WAIT_RATE_LIMITED
import com.desolate.elisium.engine.WAIT_SIGNING_IN
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.settings.FasterDownloads
import com.desolate.elisium.settings.Settings
import com.desolate.elisium.ui.downloads.QueueViewModel
import com.desolate.elisium.ui.downloads.STALL_AFTER_MS
import com.desolate.elisium.ui.downloads.sideAt
import com.desolate.elisium.ui.downloads.stallReasonFor
import com.desolate.elisium.ui.downloads.stallSide
import com.desolate.elisium.ui.downloads.toRowModel
import com.desolate.elisium.ui.settings.FASTER_DOWNLOADS_HELP
import com.desolate.elisium.ui.settings.FASTER_DOWNLOADS_TITLE
import com.desolate.elisium.ui.settings.SettingsViewModel
import com.desolate.elisium.ui.settings.fasterDownloadsChoices
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class FasterFeelTest {
    // -- instant card -------------------------------------------------------
    @Test fun aQueuedOrProbingCardShowsTheHostAtOnce() {
        assertEquals("youtube.com", queueItem(state = "queued", url = "https://www.youtube.com/watch?v=abc").toRowModel().title)
        assertEquals("vimeo.com", queueItem(state = "probing", url = "https://vimeo.com/123").toRowModel().title)
        assertEquals("Real", queueItem(state = "queued", title = "Real").toRowModel().title)
    }

    // -- "Starting..." with a reason ------------------------------------------
    @Test fun stallReasonPriorityAndWords() {
        assertEquals("Rate limited, waiting", stallReasonFor(WAIT_RATE_LIMITED, true))
        assertEquals("Waiting for Wi-Fi", stallReasonFor(WAIT_SIGNING_IN, true))
        assertEquals("Waiting for the network", stallReasonFor(WAIT_NETWORK, false))
        assertEquals("Signing in", stallReasonFor(WAIT_SIGNING_IN, false))
        assertNull(stallReasonFor(null, false))
    }

    @Test fun stallSideSwitchesAfterTenQuietSeconds() {
        val since = 1_000L
        assertEquals("base", stallSide("base", since, "Signing in", since + STALL_AFTER_MS - 1))
        assertEquals("Starting... Signing in", stallSide("base", since, "Signing in", since + STALL_AFTER_MS))
        assertEquals("Starting...", stallSide("base", since, null, since + 60_000))
        assertEquals("base", stallSide("base", null, "Signing in", since + 60_000)) // a row that is moving
    }

    @Test fun onlyRowsStillStartingCarryTheStamp() {
        val starting = queueItem(state = "downloading").copy(quietSince = 5L, waitHint = WAIT_SIGNING_IN).toRowModel()
        assertEquals(5L, starting.startingSince)
        assertEquals("Starting", starting.side)
        assertEquals("Starting... Signing in", starting.sideAt(5L + STALL_AFTER_MS))
        val probing = queueItem(state = "probing").copy(quietSince = 7L).toRowModel()
        assertEquals(7L, probing.startingSince)
        assertEquals("Looking at the link", probing.side)
        val moving = queueItem(state = "downloading", percent = 10.0, speed = 1_000_000.0).copy(quietSince = 5L).toRowModel()
        assertNull(moving.startingSince)
        assertEquals(moving.side, moving.sideAt(5L + 60_000))
        assertNull(queueItem(state = "done").copy(quietSince = 5L).toRowModel().startingSince)
    }

    @Test fun aQueuedRowSaysWhyItWaits() {
        assertEquals("Rate limited, waiting", queueItem(state = "queued").copy(waitHint = WAIT_RATE_LIMITED).toRowModel().side)
        assertEquals("Waiting for Wi-Fi", queueItem(state = "queued").toRowModel(holdWifi = true).side)
        assertEquals("Starts next", queueItem(state = "queued").toRowModel().side)
    }

    @Test fun theWifiHoldReachesTheRows() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        gw.items.value = listOf(queueItem(1, "queued"))
        assertEquals("Starts next", vm.rows.value.single().side)
        gw.holdReason.value = WAITING_FOR_WIFI
        assertEquals("Waiting for Wi-Fi", vm.rows.value.single().side)
    }

    @Test fun accessibleTextStillSaysPercent() {
        val row = queueItem(state = "downloading", percent = 42.0, speed = 1_000_000.0).toRowModel()
        assertEquals(42, row.percent)
        assertEquals("42%", row.figure)
    }

    // -- the setting -----------------------------------------------------------------
    @Test fun fasterDownloadsRowWordsAndChoices() {
        assertEquals("Faster downloads", FASTER_DOWNLOADS_TITLE)
        assertEquals("Auto looks each link up once. Turn off if downloads fail.", FASTER_DOWNLOADS_HELP)
        assertEquals(listOf(FasterDownloads.Auto to "Auto", FasterDownloads.Off to "Off"), fasterDownloadsChoices())
    }

    @Test fun fasterDownloadsFollowsTheStoreAndSaves() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore(Settings())
        val vm = SettingsViewModel(store, backgroundScope)
        assertEquals(FasterDownloads.Auto, vm.state.value.fasterDownloads)
        vm.setFasterDownloads(FasterDownloads.Off)
        assertEquals(FasterDownloads.Off, store.state.value.fasterDownloads)
        assertEquals(FasterDownloads.Off, vm.state.value.fasterDownloads)
        vm.setFasterDownloads(FasterDownloads.Auto)
        assertTrue(vm.state.value.fasterDownloads == FasterDownloads.Auto)
        assertFalse(store.state.value.fasterDownloads == FasterDownloads.Off)
    }
}
