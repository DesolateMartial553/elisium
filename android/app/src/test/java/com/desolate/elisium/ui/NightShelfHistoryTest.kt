package com.desolate.elisium.ui

import com.desolate.elisium.engine.FakeHistory
import com.desolate.elisium.engine.FakeStore
import com.desolate.elisium.engine.HistoryRecord
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import com.desolate.elisium.ui.components.progressFraction
import com.desolate.elisium.ui.components.sampleSizeFor
import com.desolate.elisium.ui.history.FileStatus
import com.desolate.elisium.ui.history.HistoryViewModel
import com.desolate.elisium.ui.history.OpenTarget
import com.desolate.elisium.ui.history.dayHeading
import com.desolate.elisium.ui.history.filterBySite
import com.desolate.elisium.ui.history.folderDocumentId
import com.desolate.elisium.ui.history.groupByDay
import com.desolate.elisium.ui.history.openTargetFor
import com.desolate.elisium.ui.history.relativeFolderOfPath
import com.desolate.elisium.ui.history.requeueLine
import com.desolate.elisium.ui.history.siteOptions
import com.desolate.elisium.ui.history.toRowModel
import com.desolate.elisium.ui.settings.SettingsViewModel
import com.desolate.elisium.ui.settings.photoModeChoices
import com.desolate.elisium.ui.settings.songLengthChoices
import java.time.LocalDate
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private val UTC = ZoneId.of("UTC")
private val TODAY = LocalDate.of(2026, 11, 22)

private fun rec(
    id: Long,
    url: String = "https://www.youtube.com/watch?v=$id",
    title: String = "Video $id",
    finished: String = "2026-11-22T10:41:00Z",
    state: String = "done",
    path: String? = "content://media/$id",
    note: String? = null,
    files: Int? = null,
) = HistoryRecord(id, url, null, title, state, null, null, path, finished, finished, note, files)

@OptIn(ExperimentalCoroutinesApi::class)
class NightShelfHistoryTest {
    private fun row(r: HistoryRecord) = r.toRowModel({ true }, UTC, Locale.ENGLISH)

    @Test fun rowsCarryTheNoteFileCountDayAndTime() {
        val r = row(rec(1, url = "https://www.instagram.com/p/Cx/", note = "Already saved", files = 7))
        assertEquals("Already saved", r.note)
        assertEquals(7, r.filesTotal)
        assertTrue(r.multiFile)
        assertEquals(TODAY, r.day)
        assertEquals("10:41", r.time)
        assertEquals("Instagram", r.siteLabel)
        assertEquals("instagram.com", r.site)
        assertEquals(false, row(rec(2)).multiFile)
        assertNull(row(rec(3, note = " ")).note)
    }

    @Test fun dayHeadingsAreTodayYesterdayThenTheDate() {
        assertEquals("Today", dayHeading(TODAY, TODAY, Locale.ENGLISH))
        assertEquals("Yesterday", dayHeading(TODAY.minusDays(1), TODAY, Locale.ENGLISH))
        assertEquals("Thursday 19 November", dayHeading(LocalDate.of(2026, 11, 19), TODAY, Locale.ENGLISH))
        assertEquals("Wednesday 31 December 2025", dayHeading(LocalDate.of(2025, 12, 31), TODAY, Locale.ENGLISH))
    }

    @Test fun historyGroupsByDayKeepingNewestFirst() {
        val rows = listOf(
            row(rec(1, finished = "2026-11-22T10:41:00Z")), row(rec(2, finished = "2026-11-22T09:00:00Z")),
            row(rec(3, finished = "2026-11-21T21:04:00Z")), row(rec(4, finished = "2026-11-19T16:50:00Z")),
            row(rec(5, finished = "garbage")),
        )
        val groups = groupByDay(rows, TODAY, Locale.ENGLISH)
        assertEquals(listOf("Today", "Yesterday", "Thursday 19 November", "Earlier"), groups.map { it.heading })
        assertEquals(listOf(listOf(1L, 2L), listOf(3L), listOf(4L), listOf(5L)), groups.map { g -> g.rows.map { it.id } })
        assertEquals(emptyList<Any>(), groupByDay(emptyList(), TODAY))
    }

    @Test fun siteFilterListsSitesAndNarrowsRows() {
        val rows = listOf(
            row(rec(1)), row(rec(2, url = "https://www.instagram.com/p/a/")), row(rec(3)), row(rec(4, url = "https://www.tiktok.com/@a/photo/1")),
        )
        assertEquals(listOf("YouTube", "Instagram", "TikTok"), siteOptions(rows))
        assertEquals(listOf(1L, 3L), filterBySite(rows, "YouTube").map { it.id })
        assertEquals(4, filterBySite(rows, null).size)
        assertEquals(emptyList<Any>(), filterBySite(rows, "Vimeo"))
    }

    @Test fun viewModelGroupsAndFiltersBySite() = runTest(UnconfinedTestDispatcher()) {
        val h = FakeHistory()
        h.add("https://www.youtube.com/watch?v=1", title = "Cats", state = "done", filePath = "store://1")
        h.add("https://www.instagram.com/p/a/", title = "Dogs", state = "done", filePath = "store://2")
        val vm = HistoryViewModel(h, FakeStore(), { "x" }, backgroundScope, UnconfinedTestDispatcher(testScheduler), UTC, Locale.ENGLISH) { TODAY }
        advanceUntilIdle()
        assertEquals(setOf("YouTube", "Instagram"), vm.sites.value.toSet())
        vm.setSite("Instagram")
        assertEquals(listOf("Dogs"), vm.groups.value.flatMap { g -> g.rows.map { it.title } })
        vm.setSite(null)
        assertEquals(2, vm.groups.value.sumOf { it.rows.size })
    }

    @Test fun downloadAgainConfirmationWords() {
        assertEquals("Added 1 link", requeueLine(existed = false, stateAfter = "queued"))
        assertEquals("Retrying 1 link", requeueLine(existed = true, stateAfter = "queued"))
        assertEquals("Already downloaded, nothing new to fetch", requeueLine(existed = true, stateAfter = "done"))
    }

    @Test fun openGoesToTheFolderForMultiFilePosts() {
        assertEquals(OpenTarget.Folder, openTargetFor(multiFile = true))
        assertEquals(OpenTarget.File, openTargetFor(multiFile = false))
    }

    @Test fun folderIdsAndRelativePaths() {
        assertEquals("primary:Download/Elisium/owner", folderDocumentId("Download/Elisium/owner/"))
        assertEquals("primary:Download/Elisium", folderDocumentId("/Download/Elisium"))
        assertEquals(
            "Download/Elisium/owner",
            relativeFolderOfPath("/storage/emulated/0/Download/Elisium/owner/a [1].jpg", "/storage/emulated/0"),
        )
        assertEquals("Download/Elisium", relativeFolderOfPath("/storage/emulated/0/Download/Elisium/a.mp4", "/storage/emulated/0/"))
        assertNull(relativeFolderOfPath("/sdcard2/a.mp4", "/storage/emulated/0"))
        assertNull(relativeFolderOfPath("/storage/emulated/0/a.mp4", "/storage/emulated/0"))
        assertEquals(FileStatus.Available, row(rec(1)).fileStatus)
    }

    @Test fun photoSettingsMapToLabelsAndSaveThroughTheSetters() = runTest(UnconfinedTestDispatcher()) {
        assertEquals(PhotoMode.entries, photoModeChoices().map { it.first })
        assertEquals(SongLength.entries, songLengthChoices().map { it.first })
        assertEquals(photoModeChoices().size, photoModeChoices().map { it.second }.toSet().size)
        assertEquals(songLengthChoices().size, songLengthChoices().map { it.second }.toSet().size)
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        assertEquals(PhotoMode.PhotosSongVideo, vm.state.value.photoMode)
        assertEquals(SongLength.Snippet, vm.state.value.songLength)
        vm.setPhotoMode(PhotoMode.PhotosOnly)
        vm.setSongLength(SongLength.Full)
        advanceUntilIdle()
        assertEquals(PhotoMode.PhotosOnly, store.state.value.photoMode)
        assertEquals(SongLength.Full, store.state.value.songLength)
        assertEquals(PhotoMode.PhotosOnly, vm.state.value.photoMode)
        assertEquals(SongLength.Full, vm.state.value.songLength)
    }

    @Test fun progressMathAndThumbnailSampling() {
        assertEquals(0f, progressFraction(null), 0f)
        assertEquals(0f, progressFraction(-5), 0f)
        assertEquals(0.42f, progressFraction(42), 0.0001f)
        assertEquals(1f, progressFraction(250), 0f)
        assertEquals(1, sampleSizeFor(208, 118, 208, 118))
        assertEquals(8, sampleSizeFor(1920, 1080, 208, 118))
        assertEquals(1, sampleSizeFor(0, 0, 208, 118))
    }
}
