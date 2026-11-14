package com.desolate.elisium.ui

import com.desolate.elisium.engine.FakeHistory
import com.desolate.elisium.engine.FakeStore
import com.desolate.elisium.engine.HistoryRecord
import com.desolate.elisium.settings.Settings
import com.desolate.elisium.settings.SettingsStore
import com.desolate.elisium.ui.history.FileStatus
import com.desolate.elisium.ui.history.HistoryViewModel
import com.desolate.elisium.ui.history.mimeForName
import com.desolate.elisium.ui.history.toRowModel
import com.desolate.elisium.ui.settings.SettingsViewModel
import com.desolate.elisium.ui.settings.SPEED_LIMIT_DEBOUNCE_MS
import com.desolate.elisium.ui.settings.SpeedLimitError
import com.desolate.elisium.ui.settings.presetChoices
import com.desolate.elisium.ui.settings.speedLimitError
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private val UTC = ZoneId.of("UTC")

private fun record(
    id: Long = 1,
    url: String = "https://www.youtube.com/watch?v=abc",
    title: String? = "A video",
    state: String = "done",
    path: String? = "content://media/1",
) = HistoryRecord(id, url, null, title, state, null, null, path, "2026-11-13T10:00:00Z", "2026-11-14T18:00:00Z")

class HistoryRowsTest {
    @Test fun mapsFieldsAndFileStatus() {
        val row = record().toRowModel({ true }, UTC, Locale.ENGLISH)
        assertEquals("A video", row.title)
        assertEquals("youtube.com", row.site)
        assertEquals("14 Nov 2026", row.date)
        assertEquals(FileStatus.Available, row.fileStatus)
        assertEquals("content://media/1", row.filePath)
    }

    @Test fun missingFileIsFlaggedAndNoFileIsNone() {
        assertEquals(FileStatus.Missing, record().toRowModel({ false }, UTC, Locale.ENGLISH).fileStatus)
        assertEquals(FileStatus.None, record(state = "failed", path = null).toRowModel({ true }, UTC, Locale.ENGLISH).fileStatus)
        assertEquals(FileStatus.None, record(path = "").toRowModel({ true }, UTC, Locale.ENGLISH).fileStatus)
        // A path on a failed row is not offered for opening.
        assertEquals(FileStatus.None, record(state = "failed").toRowModel({ true }, UTC, Locale.ENGLISH).fileStatus)
    }

    @Test fun existenceIsOnlyCheckedForSavedFiles() {
        var asked = 0
        record(state = "failed", path = null).toRowModel({ asked++; true }, UTC, Locale.ENGLISH)
        assertEquals(0, asked)
        record().toRowModel({ asked++; true }, UTC, Locale.ENGLISH)
        assertEquals(1, asked)
    }

    @Test fun titleFallsBackToUrlAndDateToCreated() {
        val r = record(title = null).copy(finishedAt = null).toRowModel({ true }, UTC, Locale.ENGLISH)
        assertEquals("https://www.youtube.com/watch?v=abc", r.title)
        assertEquals("13 Nov 2026", r.date)
    }

    @Test fun mimeTypes() {
        assertEquals("video/mp4", mimeForName("/x/Clip [id].MP4"))
        assertEquals("audio/mpeg", mimeForName("a.mp3"))
        assertEquals("*/*", mimeForName("noext"))
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class HistoryViewModelTest {
    private fun fixtures(): Pair<FakeHistory, FakeStore> {
        val h = FakeHistory()
        h.add("https://a.example/1", title = "Cats", state = "done", filePath = "store://cats.mp4")
        h.add("https://b.example/2", title = "Dogs", state = "failed")
        val s = FakeStore()
        s.locations.add("store://cats.mp4")
        return h to s
    }

    @Test fun blankQueryShowsRecentNewestFirstWithFileStatus() = runTest(UnconfinedTestDispatcher()) {
        val (h, s) = fixtures()
        val vm = HistoryViewModel(h, s, { "x" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH)
        advanceUntilIdle()
        assertEquals(listOf("Dogs", "Cats"), vm.rows.value.map { it.title })
        assertEquals(FileStatus.Available, vm.rows.value.last().fileStatus)
    }

    @Test fun searchIsDebounced() = runTest(UnconfinedTestDispatcher()) {
        val (h, s) = fixtures()
        val vm = HistoryViewModel(h, s, { "x" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH)
        advanceUntilIdle()
        vm.setQuery("Cats")
        advanceTimeBy(100)
        runCurrent()
        assertEquals(2, vm.rows.value.size)
        advanceTimeBy(400)
        runCurrent()
        assertEquals(listOf("Cats"), vm.rows.value.map { it.title })
        vm.setQuery("")
        advanceUntilIdle()
        assertEquals(2, vm.rows.value.size)
    }

    @Test fun deleteRemovesTheEntryOnly() = runTest(UnconfinedTestDispatcher()) {
        val (h, s) = fixtures()
        val vm = HistoryViewModel(h, s, { "x" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH)
        advanceUntilIdle()
        vm.deleteFromHistory(1)
        advanceUntilIdle()
        assertEquals(listOf("Dogs"), vm.rows.value.map { it.title })
        // The fake store still has the file: history deletion never touches it.
        assertTrue(s.existsAt("store://cats.mp4"))
        assertEquals(emptyList<Any>(), s.forgotten.toList())
    }

    @Test fun downloadAgainRequeuesAndConfirms() = runTest(UnconfinedTestDispatcher()) {
        val (h, s) = fixtures()
        val queued = ArrayList<String>()
        val vm = HistoryViewModel(h, s, { queued.add(it); "Added 1 link" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH)
        vm.downloadAgain("https://a.example/1")
        assertEquals(listOf("https://a.example/1"), queued)
        assertEquals("Added 1 link", vm.messages.first())
    }

    @Test fun reloadPicksUpNewRows() = runTest(UnconfinedTestDispatcher()) {
        val (h, s) = fixtures()
        val vm = HistoryViewModel(h, s, { "x" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH)
        advanceUntilIdle()
        h.add("https://c.example/3", title = "Birds", state = "done", filePath = "store://missing.mp4")
        vm.reload()
        advanceUntilIdle()
        assertEquals("Birds", vm.rows.value.first().title)
        assertEquals(FileStatus.Missing, vm.rows.value.first().fileStatus)
    }
}

class FakeSettingsStore(initial: Settings = Settings()) : SettingsStore {
    val state = MutableStateFlow(initial)
    override val settings = state
    override suspend fun setConcurrency(value: Int): Boolean {
        if (value !in 1..5) return false
        state.value = state.value.copy(concurrency = value)
        return true
    }
    override suspend fun setSpeedLimit(value: String?): Boolean {
        state.value = state.value.copy(speedLimit = value)
        return true
    }
    override suspend fun setPresetId(id: String) { state.value = state.value.copy(presetId = id) }
    override suspend fun setWifiOnly(value: Boolean) { state.value = state.value.copy(wifiOnly = value) }
    override suspend fun setNotifyOnDone(value: Boolean) { state.value = state.value.copy(notifyOnDone = value) }
    override suspend fun setAppearance(value: com.desolate.elisium.settings.Appearance) { state.value = state.value.copy(appearance = value) }
    override suspend fun setReduceMotion(value: Boolean) { state.value = state.value.copy(reduceMotion = value) }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {
    @Test fun speedLimitValidation() {
        assertNull(speedLimitError(""))
        assertNull(speedLimitError("   "))
        assertNull(speedLimitError("2M"))
        assertNull(speedLimitError(" 500K "))
        assertNull(speedLimitError("1.5G"))
        assertNull(speedLimitError("300"))
        assertEquals(SpeedLimitError.Invalid, speedLimitError("2m"))
        assertEquals(SpeedLimitError.Invalid, speedLimitError("fast"))
        assertEquals(SpeedLimitError.Invalid, speedLimitError("-2M"))
        assertEquals(SpeedLimitError.Invalid, speedLimitError("2MB"))
    }

    @Test fun presetChoicesComeFromPresets() {
        val labels = presetChoices().map { it.label }
        assertEquals("Best quality", labels.first())
        assertEquals(8, labels.size)
    }

    @Test fun stateMirrorsStoredSettings() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore(Settings(concurrency = 3, speedLimit = "2M", presetId = "720p", wifiOnly = false, notifyOnDone = false))
        val vm = SettingsViewModel(store, backgroundScope)
        val s = vm.state.value
        assertEquals(3, s.concurrency)
        assertEquals("2M", s.speedLimitText)
        assertEquals("720p", s.presetId)
        assertFalse(s.wifiOnly)
        assertFalse(s.notifyOnDone)
        assertNull(s.speedLimitError)
    }

    @Test fun stepperStaysBetweenOneAndFive() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore(Settings(concurrency = 4))
        val vm = SettingsViewModel(store, backgroundScope)
        assertTrue(vm.state.value.canIncrease)
        vm.increaseConcurrency()
        assertEquals(5, store.state.value.concurrency)
        assertFalse(vm.state.value.canIncrease)
        vm.increaseConcurrency()
        assertEquals(5, store.state.value.concurrency)
        repeat(6) { vm.decreaseConcurrency() }
        assertEquals(1, store.state.value.concurrency)
        assertFalse(vm.state.value.canDecrease)
    }

    @Test fun validSpeedLimitIsStoredInvalidIsKeptOnScreenOnly() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        vm.setSpeedLimitText("2M")
        advanceTimeBy(SPEED_LIMIT_DEBOUNCE_MS + 1)
        assertEquals("2M", store.state.value.speedLimit)
        vm.setSpeedLimitText("2m")
        advanceTimeBy(SPEED_LIMIT_DEBOUNCE_MS + 1)
        assertEquals("2M", store.state.value.speedLimit) // not overwritten
        assertEquals("2m", vm.state.value.speedLimitText)
        assertEquals(SpeedLimitError.Invalid, vm.state.value.speedLimitError)
        vm.setSpeedLimitText("")
        advanceTimeBy(SPEED_LIMIT_DEBOUNCE_MS + 1)
        assertNull(store.state.value.speedLimit)
        assertNull(vm.state.value.speedLimitError)
    }

    @Test fun typingDoesNotStoreEveryPrefix() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val stored = mutableListOf<String?>()
        val spying = object : SettingsStore by store {
            override suspend fun setSpeedLimit(value: String?): Boolean { stored.add(value); return store.setSpeedLimit(value) }
        }
        val vm = SettingsViewModel(spying, backgroundScope)
        for (typed in listOf("1", "10", "10M")) {
            vm.setSpeedLimitText(typed)
            advanceTimeBy(100)
        }
        assertEquals(emptyList<String?>(), stored) // nothing saved while typing
        advanceTimeBy(SPEED_LIMIT_DEBOUNCE_MS)
        assertEquals(listOf<String?>("10M"), stored) // only the final value, never "1"
    }

    @Test fun commitStoresAtOnce() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        vm.setSpeedLimitText("5M")
        vm.commitSpeedLimit()
        assertEquals("5M", store.state.value.speedLimit)
        advanceTimeBy(SPEED_LIMIT_DEBOUNCE_MS * 2) // the pending debounce must not undo or repeat it badly
        assertEquals("5M", store.state.value.speedLimit)
    }

    @Test fun zeroIsNotAValidLimit() {
        assertEquals(SpeedLimitError.Invalid, speedLimitError("0"))
        assertEquals(SpeedLimitError.Invalid, speedLimitError("0.0M"))
        assertNull(speedLimitError("0.5M"))
    }

    @Test fun switchesAndPresetArePersisted() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        vm.setWifiOnly(false)
        vm.setNotifyOnDone(false)
        vm.setPreset("audio-mp3")
        assertFalse(store.state.value.wifiOnly)
        assertFalse(store.state.value.notifyOnDone)
        assertEquals("audio-mp3", store.state.value.presetId)
        assertEquals("audio-mp3", vm.state.value.presetId)
    }
}
