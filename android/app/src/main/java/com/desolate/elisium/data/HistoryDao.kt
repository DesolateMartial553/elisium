package com.desolate.elisium.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface HistoryDao {
    @Insert
    fun insert(row: HistoryEntity): Long

    @Update
    fun update(row: HistoryEntity): Int

    @Query("SELECT * FROM downloads WHERE id = :id")
    fun get(id: Long): HistoryEntity?

    @Query(
        "SELECT * FROM downloads" +
            " WHERE url LIKE :pattern ESCAPE '\\'" +
            "    OR video_key LIKE :pattern ESCAPE '\\'" +
            "    OR title LIKE :pattern ESCAPE '\\'" +
            " ORDER BY id DESC LIMIT :limit",
    )
    fun search(pattern: String, limit: Int): List<HistoryEntity>

    @Query("SELECT * FROM downloads ORDER BY id DESC LIMIT :limit")
    fun recent(limit: Int): List<HistoryEntity>

    @Query("UPDATE downloads SET note = :note, files_total = :filesTotal WHERE id = :id")
    fun updateExtras(id: Long, note: String?, filesTotal: Int?): Int

    @Query("DELETE FROM downloads WHERE id = :id")
    fun delete(id: Long): Int
}
