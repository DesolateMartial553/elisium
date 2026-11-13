package com.desolate.elisium.engine

import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/** The read side of an archive; the queue hands out a read-only wrapper while downloading. */
interface ArchiveView {
    fun has(extractor: String, videoId: String): Boolean
    fun remove(extractor: String, videoId: String): Boolean
}

/**
 * yt-dlp compatible download archive (port of `archive.py`): one `<extractor> <id>`
 * pair per line, extractor lower-cased. yt-dlp appends to this file too, so every
 * operation re-reads it, and writes go through a temp file + atomic move.
 * An internal lock stops one process interleaving read-modify-write cycles.
 */
open class Archive(val file: File) : ArchiveView {
    private val lock = ReentrantLock()

    private fun read(): List<Pair<String, String>> {
        val text = try {
            String(Files.readAllBytes(file.toPath()), Charsets.UTF_8)
        } catch (_: java.nio.file.NoSuchFileException) {
            return emptyList()
        }
        val entries = ArrayList<Pair<String, String>>()
        val seen = HashSet<Pair<String, String>>()
        for (line in text.split(LINE_BREAK)) {
            val fields = line.split(WHITESPACE).filter { it.isNotEmpty() }
            if (fields.size != 2) continue
            val entry = fields[0].lowercase() to fields[1]
            if (!seen.add(entry)) continue
            entries.add(entry)
        }
        return entries
    }

    /** Replaces [source] over [target] atomically. Overridable so tests can inject a failure. */
    protected open fun atomicMove(source: Path, target: Path) {
        Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    }

    private fun write(entries: List<Pair<String, String>>) {
        val payload = entries.joinToString("") { (extractor, id) -> "$extractor $id\n" }
        val parent = (file.absoluteFile.parentFile ?: File(".")).toPath()
        Files.createDirectories(parent)
        val tmp = Files.createTempFile(parent, ".${file.name}.", ".tmp")
        try {
            FileOutputStream(tmp.toFile()).use { out ->
                out.write(payload.toByteArray(Charsets.UTF_8))
                out.flush()
                out.fd.sync()
            }
            atomicMove(tmp, file.absoluteFile.toPath())
        } catch (t: Throwable) {
            try {
                Files.deleteIfExists(tmp)
            } catch (_: Exception) {
            }
            throw t
        }
    }

    private fun clean(extractor: String, videoId: String): Pair<String, String> {
        val key = extractor.pyStrip().lowercase()
        val value = videoId.pyStrip()
        if (key.isEmpty() || value.isEmpty()) throw IllegalArgumentException("extractor and id must not be empty")
        if (key.any { isPySpace(it) } || value.any { isPySpace(it) }) {
            throw IllegalArgumentException("extractor and id must not contain whitespace")
        }
        return key to value
    }

    /** True when `(extractor, id)` is archived. */
    override fun has(extractor: String, videoId: String): Boolean = lock.withLock {
        val key = extractor.pyStrip().lowercase()
        (key to videoId.pyStrip()) in read()
    }

    /** Archives one entry. Returns false if it was already there. */
    fun add(extractor: String, videoId: String): Boolean = lock.withLock {
        val entry = clean(extractor, videoId)
        val entries = read()
        if (entry in entries) return@withLock false
        write(entries + entry)
        true
    }

    /** Drops one entry. Returns false if it was not archived. */
    override fun remove(extractor: String, videoId: String): Boolean = lock.withLock {
        val entry = clean(extractor, videoId)
        val entries = read()
        if (entry !in entries) return@withLock false
        write(entries.filter { it != entry })
        true
    }

    private companion object {
        // Python str.splitlines() separators.
        val LINE_BREAK = Regex("\r\n|[\n\r\u000B\u000C\u001C-\u001E\u0085\u2028\u2029]")
        val WHITESPACE = Regex("[\\p{Z}\\s\\u0085\\u001c-\\u001f]+")
    }
}

/** `"youtube:ID"` -> `("youtube", "ID")`; null if malformed. */
internal fun splitKey(key: String): Pair<String, String>? {
    val trimmed = key.pyStrip()
    val colon = trimmed.indexOf(':')
    if (colon < 0) return null
    val head = trimmed.substring(0, colon).pyStrip().lowercase()
    val tail = trimmed.substring(colon + 1).pyStrip()
    if (head.isEmpty() || tail.isEmpty()) return null
    return head to tail
}

/**
 * True when a finished file named `... [<id>] ...` sits in [dir]. Unfinished yt-dlp
 * side files (`.part`, `.ytdl`, `.temp`) and directories never count.
 */
fun fileExistsFor(dir: File, videoId: String): Boolean {
    val needle = "[$videoId]"
    val names = dir.list() ?: return false
    for (name in names) {
        if (!name.contains(needle)) continue
        if (name.endsWith(".part") || name.endsWith(".ytdl") || name.endsWith(".temp")) continue
        if (File(dir, name).isFile) return true
    }
    return false
}

/**
 * Checks a `video_key` against the archive *and* the output location ([existsFor]).
 * True only when archived and a finished file exists. If archived but the file is
 * gone, the id is removed from the archive (so it downloads again) and false returned.
 */
fun reconcile(archive: ArchiveView, key: String, existsFor: (extractor: String, videoId: String) -> Boolean): Boolean {
    val (extractor, videoId) = splitKey(key) ?: return false
    if (!archive.has(extractor, videoId)) return false
    if (existsFor(extractor, videoId)) return true
    archive.remove(extractor, videoId)
    return false
}
