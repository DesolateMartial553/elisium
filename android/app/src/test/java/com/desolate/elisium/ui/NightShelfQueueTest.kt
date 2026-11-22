package com.desolate.elisium.ui

import com.desolate.elisium.engine.ErrorInfo
import com.desolate.elisium.ui.downloads.BarKind
import com.desolate.elisium.ui.downloads.LOOKING_UP_TITLE
import com.desolate.elisium.ui.downloads.QueueFilter
import com.desolate.elisium.ui.downloads.RowAction
import com.desolate.elisium.ui.downloads.Tone
import com.desolate.elisium.ui.downloads.applyFilter
import com.desolate.elisium.ui.downloads.filterCounts
import com.desolate.elisium.ui.downloads.filterOf
import com.desolate.elisium.ui.downloads.queueTitle
import com.desolate.elisium.ui.downloads.rowMeta
import com.desolate.elisium.ui.downloads.spokenRow
import com.desolate.elisium.ui.downloads.toRowModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private const val MB = 1024L * 1024

class NightShelfQueueTest {
    @Test fun filterChipsGroupStatesLikeTheDesktopCards() {
        assertEquals(QueueFilter.Downloading, filterOf("probing"))
        assertEquals(QueueFilter.Downloading, filterOf("downloading"))
        assertEquals(QueueFilter.Downloading, filterOf("merging"))
        assertEquals(QueueFilter.Downloading, filterOf("converting"))
        assertEquals(QueueFilter.Waiting, filterOf("queued"))
        assertEquals(QueueFilter.Waiting, filterOf("paused"))
        assertEquals(QueueFilter.Failed, filterOf("failed"))
        assertEquals(QueueFilter.Done, filterOf("done"))
        // Cancelled and skipped are only in All.
        assertNull(filterOf("cancelled"))
        assertNull(filterOf("skipped"))
    }

    @Test fun countsAndFilteringFollowTheRows() {
        val rows = listOf(
            queueItem(1, "downloading").toRowModel(), queueItem(2, "queued").toRowModel(), queueItem(3, "paused").toRowModel(),
            queueItem(4, "failed").toRowModel(), queueItem(5, "done").toRowModel(), queueItem(6, "done").toRowModel(),
            queueItem(7, "cancelled").toRowModel(),
        )
        val counts = filterCounts(rows)
        assertEquals(7, counts[QueueFilter.All])
        assertEquals(1, counts[QueueFilter.Downloading])
        assertEquals(2, counts[QueueFilter.Waiting])
        assertEquals(1, counts[QueueFilter.Failed])
        assertEquals(2, counts[QueueFilter.Done])
        assertEquals(listOf(2, 3), applyFilter(rows, QueueFilter.Waiting).map { it.id })
        assertEquals(listOf(5, 6), applyFilter(rows, QueueFilter.Done).map { it.id })
        assertEquals(7, applyFilter(rows, QueueFilter.All).size)
    }

    @Test fun zeroPrintsAsZeroNotBlank() {
        val counts = filterCounts(emptyList())
        for (f in QueueFilter.entries) assertEquals(f.name, 0, counts[f])
    }

    @Test fun downloadingRowShowsPercentSpeedAndTimeLeft() {
        val row = queueItem(
            state = "downloading", title = "Clip", url = "https://www.youtube.com/watch?v=x", percent = 42.0,
            downloaded = 12 * MB, total = 80 * MB, speed = 4.2 * MB, eta = 97.0,
        ).copy(formatLabel = "1080p MP4").toRowModel()
        assertEquals("42%", row.figure)
        assertEquals("", row.stateWord)
        assertEquals("4.2 MB/s · 1 min 37 s left", row.side)
        assertEquals("YouTube · 1080p MP4 · 80.0 MB", row.meta)
        assertEquals(BarKind.Hue, row.bar)
        assertEquals(Tone.Muted, row.tone)
    }

    @Test fun pausedRowKeepsItsPercentAndSaysHowMuchIsLeft() {
        val row = queueItem(state = "paused", percent = 40.0, downloaded = 4 * MB, total = 10 * MB).toRowModel()
        assertEquals("40%", row.figure)
        assertEquals("Paused · 6.0 MB to go", row.side)
        assertEquals(BarKind.Paused, row.bar)
    }

    @Test fun waitingCheckingDoneAndSkippedRows() {
        val waiting = queueItem(state = "queued").toRowModel()
        assertEquals("Waiting", waiting.stateWord)
        assertEquals("Starts next", waiting.side)
        assertEquals(Tone.Faint, waiting.tone)
        assertEquals(BarKind.None, waiting.bar)
        assertEquals("Checking", queueItem(state = "probing").toRowModel().stateWord)
        val done = queueItem(state = "done").copy(filePath = "content://media/1").toRowModel()
        assertEquals("Done", done.stateWord)
        assertEquals(Tone.Positive, done.tone)
        assertTrue(done.canOpen)
        assertEquals("content://media/1", done.filePath)
        assertFalse(done.multiFile)
        assertFalse(queueItem(state = "done").toRowModel().canOpen) // nothing saved to open
        val skipped = queueItem(state = "skipped").copy(note = "Already saved").toRowModel()
        assertEquals("Skipped", skipped.stateWord)
        assertEquals("Already saved", skipped.note)
    }

    @Test fun failedRowGivesTheReasonAndOneFix() {
        val row = queueItem(state = "failed", error = ErrorInfo("Instagram sign-in has expired", "Sign in", "session_expired")).toRowModel()
        assertEquals(Tone.Negative, row.tone)
        assertEquals("Instagram sign-in has expired", row.errorMessage)
        assertEquals(listOf(RowAction.Retry, RowAction.SignIn), row.actions)
        assertEquals("", row.figure)
    }

    @Test fun multiFilePostsCountFilesAndOpenTheirFolder() {
        val running = queueItem(
            state = "downloading", url = "https://www.instagram.com/p/CpostCode1/", title = "Monument Hill at dawn",
        ).copy(formatLabel = "6 photos + song", filesDone = 3, filesTotal = 7).toRowModel()
        assertEquals("Instagram · 6 photos + song · 3 of 7 files", running.meta)
        assertEquals("43%", running.figure) // no byte percent: the files give it
        assertTrue(running.multiFile)
        val done = queueItem(state = "done", url = "https://www.instagram.com/p/CpostCode1/")
            .copy(formatLabel = "6 photos + song", filesDone = 7, filesTotal = 7, filePath = "content://media/9").toRowModel()
        assertEquals("Instagram · 6 photos + song · 7 files", done.meta)
        assertTrue(done.multiFile)
        assertTrue(done.canOpen)
    }

    @Test fun theNoteShowsUnderTheMetaAndIsSpoken() {
        val row = queueItem(state = "skipped", title = "Post").copy(note = "Already saved").toRowModel()
        assertEquals("Already saved", row.note)
        assertEquals("Post, Skipped, Already saved", spokenRow("Post", "Skipped", null, row, null))
        assertNull(queueItem(state = "done").copy(note = "  ").toRowModel().note)
    }

    @Test fun postLinksSayLookingUpUntilTheProbeNamesThem() {
        for (url in listOf(
            "https://www.instagram.com/p/CpostCode1/",
            "https://www.instagram.com/stories/someone/",
            "https://www.instagram.com/stories/highlights/17900000000000001/",
            "https://www.tiktok.com/@dancer/photo/7300000000000000001",
        )) {
            for (state in listOf("queued", "probing")) {
                assertEquals("$url $state", LOOKING_UP_TITLE, queueItem(state = state, url = url).toRowModel().title)
            }
        }
        assertEquals("Looking up the post...", LOOKING_UP_TITLE)
        // Not for plain video links, not once the title is known, not once running.
        assertEquals("https://example.com/v/1", queueItem(state = "queued").toRowModel().title)
        assertEquals("https://www.instagram.com/reel/CreelCode1/", queueTitle(null, "https://www.instagram.com/reel/CreelCode1/", "queued"))
        assertEquals("Real title", queueTitle("Real title", "https://www.instagram.com/p/CpostCode1/", "probing"))
        assertEquals("https://www.instagram.com/p/CpostCode1/", queueTitle(null, "https://www.instagram.com/p/CpostCode1/", "downloading"))
    }

    @Test fun thumbnailMustBeHttpOrNothing() {
        assertEquals("https://cdn.example/a.jpg", queueItem().copy(thumbnail = "https://cdn.example/a.jpg").toRowModel().thumbnail)
        assertNull(queueItem().copy(thumbnail = "file:///etc/passwd").toRowModel().thumbnail)
        assertNull(queueItem().toRowModel().thumbnail)
        assertEquals("example.com", queueItem().toRowModel().site) // no thumbnail: the block shows the site name
    }

    @Test fun metaLineParts() {
        assertEquals("YouTube · 1080p MP4 · 648.5 MB", rowMeta("YouTube", "1080p MP4", null, null, "done", (648.5 * MB).toLong()))
        assertEquals("YouTube", rowMeta("YouTube", null, null, null, "queued", null))
        assertEquals("TikTok · 4 photos + sound · 0 of 5 files", rowMeta("TikTok", "4 photos + sound", null, 5, "downloading", null))
    }

    @Test fun etaAndSiteWordsMatchTheDesktop() {
        assertEquals("7 s", etaText(7.0))
        assertEquals("1 min 37 s", etaText(97.0))
        assertEquals("2 min", etaText(120.0))
        assertEquals("1 h 5 min", etaText(3900.0))
        assertEquals("1 h", etaText(3600.0))
        assertEquals("", etaText(null))
        assertEquals("", etaText(-1.0))
        assertEquals("YouTube", siteName("https://www.youtube.com/watch?v=1"))
        assertEquals("YouTube", siteName("https://youtu.be/abc"))
        assertEquals("Instagram", siteName("https://www.instagram.com/p/x/"))
        assertEquals("TikTok", siteName("https://vm.tiktok.com/ZM/"))
        assertEquals("X", siteName("https://x.com/a/status/1"))
        assertEquals("example.org", siteName("https://www.example.org/x"))
        assertEquals("not a url", siteName("not a url"))
    }
}
