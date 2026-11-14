package com.desolate.elisium.ui

import java.time.ZoneId
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Test

class FormattersTest {
    @Test fun bytesScaleAndRound() {
        assertEquals("", formatBytes(null as Double?))
        assertEquals("", formatBytes(-1.0))
        assertEquals("0 B", formatBytes(0L))
        assertEquals("512 B", formatBytes(512L))
        assertEquals("1.0 KB", formatBytes(1024L))
        assertEquals("12.4 MB", formatBytes((12.4 * 1024 * 1024).toLong()))
        assertEquals("1.5 GB", formatBytes((1.5 * 1024 * 1024 * 1024).toLong()))
        assertEquals("2048.0 TB", formatBytes(2048.0 * 1024 * 1024 * 1024 * 1024))
    }

    @Test fun speed() {
        assertEquals("", formatSpeed(null))
        assertEquals("", formatSpeed(0.0))
        assertEquals("2.1 MB/s", formatSpeed(2.1 * 1024 * 1024))
        assertEquals("", speedWords(null))
        assertEquals("2.0 megabytes per second", speedWords(2.0 * 1024 * 1024))
        assertEquals("300 bytes per second", speedWords(300.0))
    }

    @Test fun eta() {
        assertEquals("", formatEta(null))
        assertEquals("", formatEta(-1.0))
        assertEquals("40s", formatEta(40.0))
        assertEquals("0s", formatEta(0.0))
        assertEquals("2m", formatEta(120.0))
        assertEquals("2m 5s", formatEta(125.0))
        assertEquals("1h", formatEta(3600.0))
        assertEquals("1h 3m", formatEta(3780.0))
    }

    @Test fun etaWords() {
        assertEquals("", etaWords(null))
        assertEquals("1 second left", etaWords(1.0))
        assertEquals("40 seconds left", etaWords(40.0))
        assertEquals("2 minutes 5 seconds left", etaWords(125.0))
        assertEquals("1 hour 1 minute left", etaWords(3660.0))
        assertEquals("0 seconds left", etaWords(0.0))
    }

    @Test fun progressLineJoinsKnownParts() {
        val mb = 1024L * 1024
        assertEquals(
            "2.1 MB/s - 12.4 MB of 80.0 MB - 40s left",
            progressLine((12.4 * mb).toLong(), 80 * mb, 2.1 * mb, 40.0),
        )
        assertEquals("1.0 MB/s - 5.0 MB", progressLine(5 * mb, null, 1.0 * mb, null))
        assertEquals("", progressLine(null, null, null, null))
        assertEquals("40s left", progressLine(null, null, null, 40.0))
        assertEquals("5.0 MB", progressLine(5 * mb, 0L, null, null))
    }

    @Test fun site() {
        assertEquals("youtube.com", siteOf("https://www.youtube.com/watch?v=x"))
        assertEquals("example.org", siteOf("  https://example.org/a "))
        assertEquals("not a url", siteOf("not a url"))
    }

    @Test fun historyDate() {
        val utc = ZoneId.of("UTC")
        assertEquals("14 Nov 2026", formatHistoryDate("2026-11-14T18:00:00Z", utc, Locale.ENGLISH))
        assertEquals("15 Nov 2026", formatHistoryDate("2026-11-14T23:30:00Z", ZoneId.of("Asia/Tokyo"), Locale.ENGLISH))
        assertEquals("garbage", formatHistoryDate("garbage", utc, Locale.ENGLISH))
        assertEquals("", formatHistoryDate(null, utc, Locale.ENGLISH))
    }

    @Test fun everyStateHasALabel() {
        val states = listOf("queued", "probing", "downloading", "merging", "converting", "paused", "done", "failed", "skipped", "cancelled")
        val ids = states.map { stateLabelRes(it) }
        assertEquals(states.size, ids.toSet().size)
    }
}
