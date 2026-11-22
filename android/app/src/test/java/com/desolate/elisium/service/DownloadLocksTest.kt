package com.desolate.elisium.service

import com.desolate.elisium.ui.queueItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeLock(val log: MutableList<String>, val name: String, val failOnAcquire: Boolean = false) : HeldLock {
    override fun acquire() {
        log.add("$name+")
        if (failOnAcquire) throw SecurityException("no permission")
    }

    override fun release() {
        log.add("$name-")
    }
}

class DownloadLocksTest {
    @Test fun heldWhileAnythingRunsOrLooksUpALink() {
        assertFalse(shouldHoldLocks(emptyList()))
        for (state in listOf("probing", "downloading", "merging", "converting")) {
            assertTrue(state, shouldHoldLocks(listOf(queueItem(1, "done"), queueItem(2, state))))
        }
        for (state in listOf("queued", "paused", "done", "failed", "skipped", "cancelled")) {
            assertFalse(state, shouldHoldLocks(listOf(queueItem(1, state))))
        }
    }

    @Test fun acquiresOnceWhenDownloadingStartsAndReleasesWhenItStops() {
        val log = ArrayList<String>()
        val locks = DownloadLocks(listOf(FakeLock(log, "wifi"), FakeLock(log, "cpu")))
        locks.update(false)
        assertTrue(log.isEmpty())
        locks.update(true)
        locks.update(true) // the next progress tick: nothing more to do
        assertEquals(listOf("wifi+", "cpu+"), log)
        assertTrue(locks.isHeld)
        locks.update(false)
        assertEquals(listOf("wifi+", "cpu+", "wifi-", "cpu-"), log)
        assertFalse(locks.isHeld)
        locks.update(false)
        locks.releaseAll() // idle, error and destroy may all call it: only the first one releases
        assertEquals(4, log.size)
    }

    @Test fun releaseAllLetsGoOnErrorOrDestroyAndANewDownloadAcquiresAgain() {
        val log = ArrayList<String>()
        val locks = DownloadLocks(listOf(FakeLock(log, "wifi")))
        locks.update(true)
        locks.releaseAll()
        assertFalse(locks.isHeld)
        locks.update(true)
        assertEquals(listOf("wifi+", "wifi-", "wifi+"), log)
    }

    @Test fun aLockThatCannotBeTakenDoesNotStopTheOtherOrTheRelease() {
        val log = ArrayList<String>()
        val locks = DownloadLocks(listOf(FakeLock(log, "wifi", failOnAcquire = true), FakeLock(log, "cpu")))
        locks.update(true)
        assertEquals(listOf("wifi+", "cpu+"), log)
        locks.update(false)
        assertEquals(listOf("wifi+", "cpu+", "wifi-", "cpu-"), log)
    }
}
