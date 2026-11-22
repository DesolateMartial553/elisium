package com.desolate.elisium.data

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * Version 1 to 2 (brief 10D): history rows for photo posts, carousels and stories gain a `note`
 * ("Already saved", a song note) and `files_total`. Both columns are nullable with no default, so rows
 * written by version 1 stay valid and read back as null.
 */
val MIGRATION_1_2_SQL: List<String> = listOf(
    "ALTER TABLE `downloads` ADD COLUMN `note` TEXT",
    "ALTER TABLE `downloads` ADD COLUMN `files_total` INTEGER",
)

val MIGRATION_1_2: Migration = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        MIGRATION_1_2_SQL.forEach { db.execSQL(it) }
    }
}
