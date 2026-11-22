package com.desolate.elisium.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SettingsRulesTest {
    @Test
    fun defaultsMatchTheBrief() {
        val s = Settings()
        assertEquals(2, s.concurrency)
        assertNull(s.speedLimit)
        assertEquals("best", s.presetId)
        assertTrue(s.wifiOnly)
        assertTrue(s.notifyOnDone)
        assertEquals(FasterDownloads.Auto, s.fasterDownloads)
    }

    @Test
    fun fasterDownloadsStoredValuesFallBackToAuto() {
        assertEquals(FasterDownloads.Auto, FasterDownloads.fromStored(null))
        assertEquals(FasterDownloads.Auto, FasterDownloads.fromStored("auto"))
        assertEquals(FasterDownloads.Off, FasterDownloads.fromStored("off"))
        assertEquals(FasterDownloads.Auto, FasterDownloads.fromStored("turbo")) // junk or an older file
        for (mode in FasterDownloads.entries) assertEquals(mode, FasterDownloads.fromStored(mode.storedValue))
    }

    @Test
    fun validSpeedLimits() {
        assertEquals("2M", validSpeedLimit("2M"))
        assertEquals("500K", validSpeedLimit(" 500K "))
        assertEquals("1.5M", validSpeedLimit("1.5M"))
        assertEquals("1G", validSpeedLimit("1G"))
        assertEquals("100", validSpeedLimit("100"))
    }

    @Test
    fun invalidSpeedLimits() {
        for (bad in listOf("", "  ", "fast", "2MB", "M", "-1M", "1.M", ".5M", "2 M", "1e3", "2m", "5T")) {
            assertNull("'$bad' should be rejected", validSpeedLimit(bad))
        }
        assertNull(validSpeedLimit(null))
    }

    @Test
    fun concurrencyRange() {
        for (n in 1..5) assertTrue(isValidConcurrency(n))
        assertFalse(isValidConcurrency(0))
        assertFalse(isValidConcurrency(6))
        assertFalse(isValidConcurrency(-1))
        assertEquals(4, validConcurrency(4))
        assertEquals(2, validConcurrency(0))
        assertEquals(2, validConcurrency(9))
        assertEquals(2, validConcurrency(null))
    }

    @Test
    fun presetFallsBackToTheDefault() {
        assertEquals("720p", validPresetId("720p"))
        assertEquals("best", validPresetId("nonsense"))
        assertEquals("best", validPresetId(null))
    }

    @Test
    fun validatedReplacesEveryInvalidField() {
        val s = Settings(concurrency = 99, speedLimit = "fast", presetId = "x", wifiOnly = false, notifyOnDone = false).validated()
        assertEquals(2, s.concurrency)
        assertNull(s.speedLimit)
        assertEquals("best", s.presetId)
        assertFalse(s.wifiOnly)
        assertFalse(s.notifyOnDone)
    }

    @Test
    fun validatedKeepsGoodValues() {
        val s = Settings(concurrency = 5, speedLimit = " 2M ", presetId = "audio-mp3").validated()
        assertEquals(5, s.concurrency)
        assertEquals("2M", s.speedLimit)
        assertEquals("audio-mp3", s.presetId)
    }
}
