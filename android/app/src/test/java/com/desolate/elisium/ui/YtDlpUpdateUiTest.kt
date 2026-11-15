package com.desolate.elisium.ui

import com.desolate.elisium.backend.UpdateResult
import com.desolate.elisium.backend.YtDlpUpdateService
import com.desolate.elisium.backend.YtDlpUpdater
import com.desolate.elisium.settings.Settings
import com.desolate.elisium.ui.settings.SettingsViewModel
import com.desolate.elisium.ui.settings.UpdateUi
import com.desolate.elisium.settings.validated
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

private class ScriptedUpdater(var next: UpdateResult) : YtDlpUpdater {
    var calls = 0
    override fun update(): UpdateResult { calls++; return next }
}

@OptIn(ExperimentalCoroutinesApi::class)
class YtDlpUpdateUiTest {
    private fun TestScope.vm(updater: YtDlpUpdater, active: MutableStateFlow<Boolean> = MutableStateFlow(false), store: FakeSettingsStore = FakeSettingsStore()): Pair<SettingsViewModel, FakeSettingsStore> {
        val service = YtDlpUpdateService(updater, store, UnconfinedTestDispatcher(testScheduler), { 5_000L })
        return SettingsViewModel(store, backgroundScope, updates = service, downloadsActive = active) to store
    }

    @Test fun startsIdleAndEnabled() = runTest(UnconfinedTestDispatcher()) {
        val (vm, _) = vm(ScriptedUpdater(UpdateResult.Updated("1")))
        assertEquals(UpdateUi.Idle, vm.state.value.update)
        assertTrue(vm.state.value.canUpdate)
    }

    @Test fun updatedShowsVersionAndStoresTime() = runTest(UnconfinedTestDispatcher()) {
        val (vm, store) = vm(ScriptedUpdater(UpdateResult.Updated("2026.11.01")))
        vm.updateYtDlp()
        assertEquals(UpdateUi.Updated("2026.11.01"), vm.state.value.update)
        assertEquals(5_000L, store.state.value.lastYtDlpCheck)
        assertTrue(vm.state.value.canUpdate)
    }

    @Test fun upToDateAndFailedStates() = runTest(UnconfinedTestDispatcher()) {
        val updater = ScriptedUpdater(UpdateResult.AlreadyUpToDate("9"))
        val (vm, store) = vm(updater)
        vm.updateYtDlp()
        assertEquals(UpdateUi.UpToDate("9"), vm.state.value.update)
        updater.next = UpdateResult.Failed("offline")
        vm.updateYtDlp()
        assertEquals(UpdateUi.Failed("offline"), vm.state.value.update)
        assertEquals(5_000L, store.state.value.lastYtDlpCheck) // a failure is recorded too
    }

    @Test fun buttonDisabledAndIgnoredWhileDownloadActive() = runTest(UnconfinedTestDispatcher()) {
        val active = MutableStateFlow(true)
        val updater = ScriptedUpdater(UpdateResult.Updated("1"))
        val (vm, _) = vm(updater, active)
        assertTrue(vm.state.value.downloadsActive)
        assertFalse(vm.state.value.canUpdate)
        vm.updateYtDlp()
        assertEquals(0, updater.calls)
        active.value = false
        assertTrue(vm.state.value.canUpdate)
    }

    @Test fun runningStateDisablesTheButtonAndSecondTapIsIgnored() = runTest(UnconfinedTestDispatcher()) {
        val updater = ScriptedUpdater(UpdateResult.Updated("3"))
        val store = FakeSettingsStore()
        // The update body waits on this dispatcher until the test lets it run, so "running" is observable.
        val io = StandardTestDispatcher(testScheduler)
        val vm = SettingsViewModel(store, backgroundScope, updates = YtDlpUpdateService(updater, store, io, { 1L }))
        vm.updateYtDlp()
        assertEquals(UpdateUi.Running, vm.state.value.update)
        assertFalse(vm.state.value.canUpdate)
        vm.updateYtDlp() // ignored while running
        runCurrent()
        assertEquals(UpdateUi.Updated("3"), vm.state.value.update)
        assertEquals(1, updater.calls)
        assertTrue(vm.state.value.canUpdate)
    }

    @Test fun timestampRoundTripsAndNeverGoesNegative() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore(Settings())
        assertEquals(0L, store.state.value.lastYtDlpCheck)
        store.setLastYtDlpCheck(123L)
        assertEquals(123L, store.settings.value.lastYtDlpCheck)
        store.setLastYtDlpCheck(-9L)
        assertEquals(0L, store.state.value.lastYtDlpCheck)
        assertEquals(0L, Settings(lastYtDlpCheck = -5).validated().lastYtDlpCheck)
    }
}
