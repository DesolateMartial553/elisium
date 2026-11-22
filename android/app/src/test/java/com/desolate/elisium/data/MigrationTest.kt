package com.desolate.elisium.data

import com.desolate.elisium.engine.HistoryRecord
import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The project has no `room-testing` dependency, so the migration is checked against the exported schemas:
 * version 2 is exactly version 1 plus the two columns, the migration SQL adds exactly those, and old rows
 * (which read both columns as null) still map.
 */
class MigrationTest {
    private fun schema(version: Int): JsonObject {
        val relative = "schemas/com.desolate.elisium.data.AppDatabase/$version.json"
        val file = listOf(File(relative), File("app/$relative")).first { it.isFile }
        return Json.parseToJsonElement(file.readText()).jsonObject
    }

    private fun columns(schema: JsonObject): Map<String, String> {
        val entity = schema["database"]!!.jsonObject["entities"]!!.jsonArray
            .map { it.jsonObject }.single { it["tableName"]!!.jsonPrimitive.content == "downloads" }
        return (entity["fields"] as JsonArray).map { it.jsonObject }
            .associate { it["columnName"]!!.jsonPrimitive.content to it["affinity"]!!.jsonPrimitive.content }
    }

    @Test
    fun `the database is at version 2 and the migration goes from 1 to 2`() {
        assertEquals(2, schema(2)["database"]!!.jsonObject["version"]!!.jsonPrimitive.content.toInt())
        assertEquals(1, schema(1)["database"]!!.jsonObject["version"]!!.jsonPrimitive.content.toInt())
        assertEquals(1, MIGRATION_1_2.startVersion)
        assertEquals(2, MIGRATION_1_2.endVersion)
    }

    @Test
    fun `version 2 is version 1 plus note and files_total`() {
        val v1 = columns(schema(1))
        val v2 = columns(schema(2))
        assertTrue(v2.keys.containsAll(v1.keys))
        assertEquals(mapOf("note" to "TEXT", "files_total" to "INTEGER"), v2.filterKeys { it !in v1 })
        assertEquals(v1, v2.filterKeys { it in v1 }) // nothing else changed
    }

    @Test
    fun `the migration sql adds exactly the new nullable columns`() {
        assertEquals(
            listOf(
                "ALTER TABLE `downloads` ADD COLUMN `note` TEXT",
                "ALTER TABLE `downloads` ADD COLUMN `files_total` INTEGER",
            ),
            MIGRATION_1_2_SQL,
        )
        // nullable, no default: an old row stays valid and reads back as null
        assertTrue(MIGRATION_1_2_SQL.none { "NOT NULL" in it || "DEFAULT" in it })
        val fields = (schema(2)["database"]!!.jsonObject["entities"]!!.jsonArray[0].jsonObject["fields"] as JsonArray)
            .map { it.jsonObject }.filter { it["columnName"]!!.jsonPrimitive.content in setOf("note", "files_total") }
        assertEquals(2, fields.size)
        // Room writes "notNull": true only for NOT NULL columns, so both new ones are nullable
        assertTrue(fields.none { "notNull" in it })
    }

    @Test
    fun `an old row has no note and no file count, and a new row defaults the same way`() {
        val old = HistoryEntity(1, "u", null, null, "done", null, null, null, "t", "t")
        assertNull(old.note)
        assertNull(old.filesTotal)
        val record = old.toRecord()
        assertNull(record.note)
        assertNull(record.filesTotal)
        val legacy = HistoryRecord(1, "u", null, "t", "done", null, null, "p", "c", "f") // the ten-field shape
        assertNull(legacy.note)
        val fresh = newEntity("u", null, null, "queued", null, null, null, "now")
        assertNull(fresh.note)
        assertNull(fresh.filesTotal)
    }

    private class MemoryDao : HistoryDao {
        val rows = LinkedHashMap<Long, HistoryEntity>()
        private var next = 1L
        override fun insert(row: HistoryEntity): Long = next++.also { rows[it] = row.copy(id = it) }
        override fun update(row: HistoryEntity): Int { rows[row.id] = row; return 1 }
        override fun get(id: Long): HistoryEntity? = rows[id]
        override fun search(pattern: String, limit: Int): List<HistoryEntity> = rows.values.toList()
        override fun recent(limit: Int): List<HistoryEntity> = rows.values.toList()
        override fun updateExtras(id: Long, note: String?, filesTotal: Int?): Int {
            val row = rows[id] ?: return 0
            rows[id] = row.copy(note = note, filesTotal = filesTotal)
            return 1
        }
        override fun delete(id: Long): Int = if (rows.remove(id) != null) 1 else 0
    }

    @Test
    fun `the room store saves the note and the file count and reads them back`() {
        val store = RoomHistoryStore(MemoryDao(), now = { "2026-11-22T10:00:00Z" })
        val id = store.add("https://www.instagram.com/p/AbC/")
        assertNull(store.get(id)!!.note)
        assertTrue(store.updateExtras(id, "Already saved", 5))
        assertEquals("Already saved", store.get(id)!!.note)
        assertEquals(5, store.get(id)!!.filesTotal)
        store.updateState(id, "done") // a state change keeps them
        assertEquals("Already saved", store.get(id)!!.note)
        assertEquals(false, store.updateExtras(999, "x", 1))
    }
}
