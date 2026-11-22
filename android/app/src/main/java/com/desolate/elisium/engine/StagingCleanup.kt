package com.desolate.elisium.engine

import java.io.File
import java.security.MessageDigest

/*
 * Cleanup of the staging folder (`filesDir/staging`): yt-dlp writes finished files there and keeps
 * `.part` files in `staging/tmp` between a pause and a resume. Pure file logic, JVM-tested.
 */

/** Partial-download names yt-dlp resumes from (`.part`, `.ytdl` state file, `.part-FragN`). */
fun isPartialName(name: String): Boolean =
    name.endsWith(".part") || name.endsWith(".ytdl") || ".part-Frag" in name

/** The two folders yt-dlp writes into: staging itself and its `tmp` folder. */
private fun stagingFolders(stagingDir: File): List<File> = listOf(stagingDir, File(stagingDir, "tmp"))

/**
 * Deletes what the item left in staging: its `<processId>.path` file and every file named
 * `... [<videoId>] ...`. With [keepPartial] the partial files stay so a retry or resume can continue.
 * Returns how many files were deleted. A blank [videoId] never matches by name.
 */
fun deleteItemLeftovers(stagingDir: File, processId: String, videoId: String?, keepPartial: Boolean): Int {
    var deleted = 0
    if (File(stagingDir, "$processId.path").let { it.isFile && it.delete() }) deleted++
    if (videoId.isNullOrBlank()) return deleted
    val marker = "[$videoId]"
    for (folder in stagingFolders(stagingDir)) {
        val names = folder.list() ?: continue
        for (name in names) {
            if (marker !in name) continue
            if (keepPartial && isPartialName(name)) continue
            val file = File(folder, name)
            if (file.isFile && file.delete()) deleted++
        }
    }
    return deleted
}

/**
 * The media engine's folder for one item: `staging/media/<sha1(identity)[:16]>`. Stable for one link, so a restart
 * resumes in the same folder, and two items can never share files (item ids restart at 1 every launch).
 */
fun mediaDirFor(stagingDir: File, identity: String): File {
    val digest = MessageDigest.getInstance("SHA-1").digest(identity.toByteArray(Charsets.UTF_8))
    val hex = digest.joinToString("") { "%02x".format(it) }.take(16)
    return File(File(stagingDir, "media"), hex)
}

/** Deletes [dir] and what is inside it (files and one level of work folders). Never throws. */
fun deleteDirectory(dir: File): Boolean {
    return try {
        dir.walkBottomUp().forEach { it.delete() }
        !dir.exists()
    } catch (_: Exception) {
        false
    }
}

/** Seven days: orphans (files no queue item owns any more) older than this are removed at app start. */
const val ORPHAN_MAX_AGE_MS: Long = 7L * 24 * 60 * 60 * 1000

/**
 * Removes files in staging (and `staging/tmp`) last modified more than [maxAgeMs] before [now]. The queue
 * is memory-only, so at app start every staged file is an orphan; recent ones are kept for a few days
 * in case the user wants to look. Returns how many files were deleted.
 */
fun sweepOrphans(stagingDir: File, maxAgeMs: Long = ORPHAN_MAX_AGE_MS, now: Long = System.currentTimeMillis()): Int {
    var deleted = 0
    for (folder in stagingFolders(stagingDir)) {
        val files = folder.listFiles() ?: continue
        for (file in files) {
            if (file.isFile && now - file.lastModified() > maxAgeMs && file.delete()) deleted++
        }
    }
    // The media engine's per-item folders: old files go, and a folder left empty goes with them.
    for (itemDir in File(stagingDir, "media").listFiles().orEmpty()) {
        if (!itemDir.isDirectory) continue
        for (file in itemDir.walkBottomUp()) {
            if (file == itemDir) continue
            if (file.isFile && now - file.lastModified() > maxAgeMs && file.delete()) deleted++
            else if (file.isDirectory && file.list().isNullOrEmpty()) file.delete()
        }
        if (itemDir.list().isNullOrEmpty()) itemDir.delete()
    }
    return deleted
}
