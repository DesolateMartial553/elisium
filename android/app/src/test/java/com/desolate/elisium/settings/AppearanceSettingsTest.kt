package com.desolate.elisium.settings

import com.desolate.elisium.ui.FakeSettingsStore
import com.desolate.elisium.ui.settings.SettingsViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AppearanceSettingsTest {
    @Test fun defaultsAreSystemAndMotionOn() {
        val s = Settings()
        assertEquals(Appearance.System, s.appearance)
        assertEquals(false, s.reduceMotion)
    }

    @Test fun storedValuesRoundTripAndUnknownFallsBack() {
        for (a in Appearance.entries) assertEquals(a, Appearance.fromStored(a.storedValue))
        assertEquals(Appearance.System, Appearance.fromStored(null))
        assertEquals(Appearance.System, Appearance.fromStored("sepia"))
    }

    @Test fun oldSettingsStillValidate() {
        // Settings built the way an older app version stored them (no appearance keys) keep working.
        val old = Settings(concurrency = 3, speedLimit = "2M", presetId = "720p", wifiOnly = false, notifyOnDone = false).validated()
        assertEquals(Appearance.System, old.appearance)
        assertEquals(3, old.concurrency)
    }

    @Test fun viewModelRoundTrip() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        assertEquals(Appearance.System, vm.state.value.appearance)
        assertEquals(false, vm.state.value.reduceMotion)
        vm.setAppearance(Appearance.Night)
        vm.setReduceMotion(true)
        assertEquals(Appearance.Night, store.settings.first().appearance)
        assertEquals(Appearance.Night, vm.state.value.appearance)
        assertEquals(true, vm.state.value.reduceMotion)
    }
}
