package com.desolate.elisium.engine

import com.desolate.elisium.media.MediaRoute
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class FasterDownloadsTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val usable = json("""{"id": "x", "formats": [{"format_id": "18"}]}""")

    // -- reuse rules ---------------------------------------------------------
    @Test fun usableInfoIsAnObjectWithFormatsOrUrlUnderFiveMinutes() {
        assertTrue(infoIsUsable(usable, 0))
        assertTrue(infoIsUsable(json("""{"url": "https://cdn.example/v.mp4"}"""), 1_000))
        assertTrue(infoIsUsable(usable, 299_999))
        assertFalse(infoIsUsable(usable, 300_000)) // 300 s is already too old
        assertFalse(infoIsUsable(usable, -1))
        assertFalse(infoIsUsable(null, 0))
        assertFalse(infoIsUsable(json("""{"id": "x"}"""), 0))
        assertFalse(infoIsUsable(json("""{"id": "x", "formats": []}"""), 0))
        assertFalse(infoIsUsable(json("""{"_type": "playlist", "formats": [{"format_id": "1"}]}"""), 0))
        assertFalse(infoIsUsable(json("""{"_type": "playlist", "url": "https://x/y"}"""), 0))
        assertFalse(infoIsUsable(json("""{"_type": "multi_video", "url": "https://x/y"}"""), 0))
    }

    @Test fun reuseNeedsAutoAndAPlainRouteAndASiteNotLimitedAndNoSignedInSite() {
        val yt = "https://www.youtube.com/watch?v=abc"
        assertTrue(mayReuseProbe(yt, true, MediaRoute.YTDLP, emptySet(), false))
        assertFalse(mayReuseProbe(yt, false, MediaRoute.YTDLP, emptySet(), false)) // Off
        assertFalse(mayReuseProbe(yt, true, MediaRoute.MEDIA, emptySet(), false)) // media engine
        assertFalse(mayReuseProbe(yt, true, MediaRoute.YTDLP, setOf("youtube.com"), false)) // 429 this session
        assertTrue(mayReuseProbe(yt, true, MediaRoute.YTDLP, setOf("vimeo.com"), false)) // another site is fine
        assertFalse(mayReuseProbe("https://www.instagram.com/reel/x/", true, MediaRoute.YTDLP_THEN_MEDIA, emptySet(), true))
        assertTrue(mayReuseProbe("https://www.instagram.com/reel/x/", true, MediaRoute.YTDLP_THEN_MEDIA, emptySet(), false))
        assertFalse(mayReuseProbe("https://www.tiktok.com/@a/video/1", true, MediaRoute.YTDLP, emptySet(), true))
        assertTrue(mayReuseProbe(yt, true, MediaRoute.YTDLP, emptySet(), true)) // cookies only matter for IG / TikTok
    }

    @Test fun siteKeyIsStablePerSite() {
        assertEquals("youtube.com", siteKey("https://www.youtube.com/watch?v=a"))
        assertEquals("youtube.com", siteKey("https://m.youtube.com/watch?v=a"))
        assertEquals("youtube.com", siteKey("https://youtu.be/a"))
        assertEquals("bbc.co.uk", siteKey("https://www.bbc.co.uk/iplayer"))
        assertEquals("vimeo.com", siteKey("https://VIMEO.com./1"))
        assertEquals("", siteKey("not a link"))
        assertEquals("", siteKey(null))
    }

    @Test fun rateLimitCodes() {
        assertTrue(isRateLimitCode("http_429"))
        assertTrue(isRateLimitCode("rate_limited"))
        assertFalse(isRateLimitCode("network"))
        assertFalse(isRateLimitCode(null))
    }

    @Test fun aLimitedSiteRunsOneAtATime() {
        assertTrue(siteSlotFree("youtube.com", emptySet(), listOf("youtube.com")))
        assertTrue(siteSlotFree("youtube.com", setOf("youtube.com"), emptyList()))
        assertFalse(siteSlotFree("youtube.com", setOf("youtube.com"), listOf("youtube.com", "vimeo.com")))
        assertTrue(siteSlotFree("vimeo.com", setOf("youtube.com"), listOf("youtube.com")))
    }

    @Test fun rerunFromTheLinkRules() {
        assertTrue(shouldRerunFromUrl("unknown", "ERROR: odd", sawProgress = false)) // before the first progress line
        assertTrue(shouldRerunFromUrl("http_403", "", sawProgress = true))
        assertTrue(shouldRerunFromUrl("format_unavailable", "", sawProgress = true))
        assertTrue(shouldRerunFromUrl("unknown", "ERROR: unable to download: HTTP Error 410: Gone", sawProgress = true))
        assertTrue(shouldRerunFromUrl("unknown", "The download link has expired", sawProgress = true))
        assertFalse(shouldRerunFromUrl("unknown", "ERROR: something else", sawProgress = true))
        assertFalse(shouldRerunFromUrl("network", "Connection reset", sawProgress = true))
    }

    @Test fun waitHintPriority() {
        assertEquals(WAIT_RATE_LIMITED, waitHint(rateLimited = true, retryingNetwork = true, signedIn = true))
        assertEquals(WAIT_NETWORK, waitHint(rateLimited = false, retryingNetwork = true, signedIn = true))
        assertEquals(WAIT_SIGNING_IN, waitHint(rateLimited = false, retryingNetwork = false, signedIn = true))
        assertNull(waitHint(false, false, false))
    }

    // -- the private info file -----------------------------------------------
    @Test fun infoFileIsFreshPrivateAndHoldsTheLookup() {
        val dir = tmp.newFolder("tmp")
        val file = writeInfoJson(dir, "item-1.info.json", usable)
        assertEquals(usable, json(file.readText()))
        assertEquals("rw-------", PosixFilePermissions.toString(Files.getPosixFilePermissions(file.toPath())))
        // An older file (even a link) is replaced, never written through.
        val target = tmp.newFile("target.txt")
        file.delete()
        Files.createSymbolicLink(file.toPath(), target.toPath())
        writeInfoJson(dir, "item-1.info.json", usable)
        assertEquals("", target.readText())
        assertTrue(file.isFile && !Files.isSymbolicLink(file.toPath()))
    }

    // -- steadier numbers ----------------------------------------------------
    @Test fun emaSteps() {
        assertEquals(1000.0, smoothSpeed(null, 1000.0), 1e-9)
        assertEquals(1200.0, smoothSpeed(1000.0, 2000.0), 1e-9)
        assertEquals(3000.0, smoothSpeed(1000.0, 11000.0), 1e-9) // a spike moves the average by a fifth
        assertEquals(10.0, smoothedEta(2000, 1000, 100.0)!!, 1e-9)
        assertNull(smoothedEta(null, 1000, 100.0))
        assertNull(smoothedEta(2000, 1000, 0.0))
        assertEquals(0.0, smoothedEta(1000, 1500, 100.0)!!, 1e-9)
    }

    @Test fun firstTwoSecondsAreAsReportedThenEmaThenARestart() {
        val s = SpeedSmoother()
        // Warm-up: shown as reported, kept out of the average.
        assertEquals(SmoothedProgress(5000.0, 9.0), s.update(0, 1_000, 100_000, 5000.0, 9.0))
        assertEquals(SmoothedProgress(9000.0, 8.0), s.update(1_999, 2_000, 100_000, 9000.0, 8.0))
        // The first sample after the warm-up seeds the average.
        assertEquals(1000.0, s.update(2_000, 3_000, 101_000, 1000.0, 99.0).speed!!, 1e-9)
        val next = s.update(3_000, 4_000, 101_000, 2000.0, 50.0)
        assertEquals(1200.0, next.speed!!, 1e-9)
        assertEquals((101_000 - 4_000) / 1200.0, next.eta!!, 1e-9)
        // A byte count that drops (the next stream) starts over, with its own warm-up.
        assertEquals(SmoothedProgress(7000.0, 4.0), s.update(4_000, 10, 50_000, 7000.0, 4.0))
        assertEquals(500.0, s.update(6_000, 20, 50_000, 500.0, 1.0).speed!!, 1e-9)
    }
}
