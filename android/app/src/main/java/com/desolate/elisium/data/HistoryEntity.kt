package com.desolate.elisium.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey
import com.desolate.elisium.engine.HistoryRecord

/** One download, same columns as the desktop `downloads` table. */
@Entity(tableName = "downloads")
data class HistoryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val url: String,
    @ColumnInfo(name = "video_key") val videoKey: String?,
    val title: String?,
    val state: String,
    @ColumnInfo(name = "error_code") val errorCode: String?,
    @ColumnInfo(name = "error_message") val errorMessage: String?,
    @ColumnInfo(name = "file_path") val filePath: String?,
    @ColumnInfo(name = "created_at") val createdAt: String,
    @ColumnInfo(name = "finished_at") val finishedAt: String?,
) {
    fun toRecord() = HistoryRecord(
        id, url, videoKey, title, state, errorCode, errorMessage, filePath, createdAt, finishedAt,
    )
}
