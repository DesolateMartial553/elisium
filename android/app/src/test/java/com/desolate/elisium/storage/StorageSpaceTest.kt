package com.desolate.elisium.storage

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val MB = 1024L * 1024

class StorageSpaceTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun knownSizeNeedsTheFileTwicePlusReserve() {
        assertEquals(100 * MB * 2 + StorageSpace.RESERVE_BYTES, StorageSpace.requiredFreeBytes(100 * MB))
    }

    @Test
    fun unknownOrNonPositiveSizeUsesTheMinimum() {
        assertEquals(StorageSpace.UNKNOWN_SIZE_MINIMUM_BYTES, StorageSpace.requiredFreeBytes(null))
        assertEquals(StorageSpace.UNKNOWN_SIZE_MINIMUM_BYTES, StorageSpace.requiredFreeBytes(0))
        assertEquals(StorageSpace.UNKNOWN_SIZE_MINIMUM_BYTES, StorageSpace.requiredFreeBytes(-5))
    }

    @Test
    fun hasRoomIsInclusiveAtTheBoundary() {
        val need = StorageSpace.requiredFreeBytes(10 * MB)
        assertTrue(StorageSpace.hasRoomFor(need, 10 * MB))
        assertFalse(StorageSpace.hasRoomFor(need - 1, 10 * MB))
    }

    @Test
    fun hugeSizeDoesNotOverflow() {
        assertEquals(Long.MAX_VALUE, StorageSpace.requiredFreeBytes(Long.MAX_VALUE))
        assertFalse(StorageSpace.hasRoomFor(Long.MAX_VALUE - 1, Long.MAX_VALUE))
    }

    @Test
    fun freeBytesWalksUpToAnExistingParent() {
        val missing = File(tmp.root, "a/b/c")
        assertTrue(StorageSpace.freeBytes(missing) > 0)
        assertEquals(StorageSpace.freeBytes(tmp.root), StorageSpace.freeBytes(missing))
    }
}
