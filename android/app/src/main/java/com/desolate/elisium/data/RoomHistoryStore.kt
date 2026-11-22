package com.desolate.elisium.data

import com.desolate.elisium.engine.HistoryRecord
import com.desolate.elisium.engine.HistoryStore
import java.time.Instant
import java.time.temporal.ChronoUnit

/** Seconds-resolution UTC ISO 8601, like the desktop `_now()` (`2026-11-13T18:00:00Z`). */
fun isoNow(): String = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()

/**
 * [HistoryStore] over Room. The methods are synchronous (Room blocks): call them off the
 * main thread. The queue runs on an IO scope. [now] is injectable only for tests.
 */
class RoomHistoryStore(
    private val dao: HistoryDao,
    private val now: () -> String = ::isoNow,
) : HistoryStore {
    private val lock = Any()

    override fun add(
        url: String,
        videoKey: String?,
        title: String?,
        state: String,
        errorCode: String?,
        errorMessage: String?,
        filePath: String?,
    ): Long = synchronized(lock) {
        dao.insert(newEntity(url, videoKey, title, state, errorCode, errorMessage, filePath, now()))
    }

    override fun updateState(
        recordId: Long,
        state: String,
        errorCode: String?,
        errorMessage: String?,
        filePath: String?,
        clearError: Boolean,
    ): Boolean = synchronized(lock) {
        checkState(state)
        val row = dao.get(recordId) ?: return false
        dao.update(applyStateUpdate(row, state, errorCode, errorMessage, filePath, clearError, now())) > 0
    }

    override fun updateExtras(recordId: Long, note: String?, filesTotal: Int?): Boolean =
        synchronized(lock) { dao.updateExtras(recordId, note, filesTotal) > 0 }

    override fun get(recordId: Long): HistoryRecord? = dao.get(recordId)?.toRecord()

    override fun search(text: String, limit: Int?): List<HistoryRecord> {
        val needle = text.trim()
        if (needle.isEmpty()) return emptyList()
        if (limit != null && limit <= 0) return emptyList()
        return dao.search(likePattern(needle), limit ?: -1).map { it.toRecord() }
    }

    override fun recent(limit: Int): List<HistoryRecord> =
        if (limit <= 0) emptyList() else dao.recent(limit).map { it.toRecord() }

    override fun delete(recordId: Long): Boolean = synchronized(lock) { dao.delete(recordId) > 0 }
}
