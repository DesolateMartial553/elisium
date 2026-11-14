package com.desolate.elisium.storage

import java.io.File

/**
 * Free-space rule for staging. A finished file is written to the staging folder and then
 * copied to Download/Elisium, so the file needs room twice (briefly), plus a reserve.
 */
object StorageSpace {
    const val RESERVE_BYTES: Long = 50L * 1024 * 1024

    /** Needed when yt-dlp has not told us the size yet. */
    const val UNKNOWN_SIZE_MINIMUM_BYTES: Long = 200L * 1024 * 1024

    /** Bytes that must be free before downloading a file of [expectedBytes] (null = unknown). */
    fun requiredFreeBytes(expectedBytes: Long?): Long {
        if (expectedBytes == null || expectedBytes <= 0L) return UNKNOWN_SIZE_MINIMUM_BYTES
        val doubled = if (expectedBytes > (Long.MAX_VALUE - RESERVE_BYTES) / 2) Long.MAX_VALUE else expectedBytes * 2 + RESERVE_BYTES
        return doubled
    }

    fun hasRoomFor(freeBytes: Long, expectedBytes: Long?): Boolean = freeBytes >= requiredFreeBytes(expectedBytes)

    /** Usable bytes on the volume that holds [dir] (its nearest existing parent). */
    fun freeBytes(dir: File): Long {
        var probe: File? = dir
        while (probe != null && !probe.exists()) probe = probe.parentFile
        return probe?.usableSpace ?: 0L
    }
}
