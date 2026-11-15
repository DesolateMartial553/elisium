package com.desolate.elisium.backend

import com.desolate.elisium.settings.Settings
import com.desolate.elisium.ui.FakeSettingsStore
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeUpdater(private val outcome: () -> UpdateResult) : YtDlpUpdater {
    var calls = 0
    override fun update(): UpdateResult { calls++; return outcome() }
}

@OptIn(ExperimentalCoroutinesApi::class)
class YtDlpUpdateServiceTest {
    private val now = 10L * AUTO_UPDATE_INTERVAL_MS

    @Test fun recordsTimeAfterSuccessAndFailure() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val ok = YtDlpUpdateService(FakeUpdater { UpdateResult.Updated("1") }, store, UnconfinedTestDispatcher(testScheduler), { now })
        assertEquals(UpdateResult.Updated("1"), ok.run())
        assertEquals(now, store.state.value.lastYtDlpCheck)

        val store2 = FakeSettingsStore()
        val bad = YtDlpUpdateService(FakeUpdater { UpdateResult.Failed("offline") }, store2, UnconfinedTestDispatcher(testScheduler), { now })
        assertEquals(UpdateResult.Failed("offline"), bad.run())
        assertEquals(now, store2.state.value.lastYtDlpCheck)
    }

    @Test fun anythingThrownBecomesFailedAndIsRecorded() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val updater = FakeUpdater { throw UnsatisfiedLinkError("no lib") }
        val svc = YtDlpUpdateService(updater, store, UnconfinedTestDispatcher(testScheduler), { now })
        assertEquals(UpdateResult.Failed("no lib"), svc.run())
        assertEquals(now, store.state.value.lastYtDlpCheck)
        assertTrue(!svc.running.value)
    }

    @Test fun autoUpdateRespectsThePolicy() = runTest(UnconfinedTestDispatcher()) {
        val recent = FakeSettingsStore(Settings(lastYtDlpCheck = now - 1000))
        val updater = FakeUpdater { UpdateResult.AlreadyUpToDate("1") }
        val svc = YtDlpUpdateService(updater, recent, UnconfinedTestDispatcher(testScheduler), { now })
        assertNull(svc.autoUpdateIfDue(onWifi = true, downloadsActive = false))
        assertEquals(0, updater.calls)

        val old = FakeSettingsStore(Settings(lastYtDlpCheck = now - AUTO_UPDATE_INTERVAL_MS, wifiOnly = true))
        val svc2 = YtDlpUpdateService(updater, old, UnconfinedTestDispatcher(testScheduler), { now })
        assertNull(svc2.autoUpdateIfDue(onWifi = false, downloadsActive = false))
        assertNull(svc2.autoUpdateIfDue(onWifi = true, downloadsActive = true))
        assertEquals(0, updater.calls)
        assertEquals(UpdateResult.AlreadyUpToDate("1"), svc2.autoUpdateIfDue(onWifi = true, downloadsActive = false))
        assertEquals(1, updater.calls)
        assertEquals(now, old.state.value.lastYtDlpCheck)
    }

    @Test fun onResultSeesTheOutcome() = runTest(UnconfinedTestDispatcher()) {
        val seen = mutableListOf<UpdateResult>()
        val svc = YtDlpUpdateService(
            FakeUpdater { UpdateResult.Updated("2") }, FakeSettingsStore(), UnconfinedTestDispatcher(testScheduler), { now }, seen::add,
        )
        svc.run()
        assertEquals(listOf<UpdateResult>(UpdateResult.Updated("2")), seen)
    }

    @Test fun shortReasonIsOneLineAndBounded() {
        assertEquals("boom", shortReason(RuntimeException("boom\nsecond line")))
        assertEquals("IllegalStateException", shortReason(IllegalStateException()))
        assertTrue(shortReason(RuntimeException("x".repeat(500))).length <= 80)
    }
}
