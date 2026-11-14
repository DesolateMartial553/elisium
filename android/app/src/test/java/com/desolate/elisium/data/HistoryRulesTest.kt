package com.desolate.elisium.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

private const val T0 = "2026-11-13T10:00:00Z"
private const val T1 = "2026-11-13T10:05:00Z"

private fun queued() = newEntity("https://youtu.be/x", "youtube:x", null, "queued", null, null, null, T0)

class HistoryRulesTest {
    @Test
    fun newRowTrimsTheUrlAndStampsCreatedAt() {
        val row = newEntity("  https://youtu.be/x  ", "youtube:x", "T", "queued", null, null, null, T0)
        assertEquals("https://youtu.be/x", row.url)
        assertEquals(T0, row.createdAt)
        assertNull(row.finishedAt)
        assertEquals(0L, row.id)
    }

    @Test
    fun aTerminalNewRowIsFinishedImmediately() {
        assertEquals(T0, newEntity("u", null, null, "failed", "network", "m", null, T0).finishedAt)
    }

    @Test
    fun blankUrlAndUnknownStateAreRejected() {
        assertThrows(IllegalArgumentException::class.java) { newEntity("  ", null, null, "queued", null, null, null, T0) }
        assertThrows(IllegalArgumentException::class.java) { newEntity("u", null, null, "weird", null, null, null, T0) }
    }

    @Test
    fun theStateSetMatchesTheSpec() {
        assertEquals(
            setOf("queued", "probing", "downloading", "merging", "converting", "paused", "done", "failed", "skipped", "cancelled"),
            HISTORY_STATES,
        )
    }

    @Test
    fun terminalStateStampsFinishedAtOnce() {
        val done = applyStateUpdate(queued(), "done", null, null, "/f.mp4", false, T1)
        assertEquals("done", done.state)
        assertEquals(T1, done.finishedAt)
        assertEquals("/f.mp4", done.filePath)
        val again = applyStateUpdate(done, "done", null, null, null, false, "later")
        assertEquals(T1, again.finishedAt)
    }

    @Test
    fun anActiveStateClearsFinishedAt() {
        val failed = applyStateUpdate(queued(), "failed", "network", "Network problem.", null, false, T1)
        val retry = applyStateUpdate(failed, "queued", null, null, null, false, "later")
        assertNull(retry.finishedAt)
    }

    @Test
    fun nullErrorAndFileArgumentsLeaveTheColumnsAlone() {
        val failed = applyStateUpdate(queued(), "failed", "network", "Network problem.", "/p", false, T1)
        val next = applyStateUpdate(failed, "queued", null, null, null, false, T1)
        assertEquals("network", next.errorCode)
        assertEquals("Network problem.", next.errorMessage)
        assertEquals("/p", next.filePath)
    }

    @Test
    fun clearErrorResetsBothErrorColumns() {
        val failed = applyStateUpdate(queued(), "failed", "network", "Network problem.", null, false, T1)
        val cleared = applyStateUpdate(failed, "done", null, null, null, true, T1)
        assertNull(cleared.errorCode)
        assertNull(cleared.errorMessage)
    }

    @Test
    fun clearErrorWinsOverNewErrorValues() {
        val row = applyStateUpdate(queued(), "failed", "a", "b", null, true, T1)
        assertNull(row.errorCode)
        assertNull(row.errorMessage)
    }

    @Test
    fun updateRejectsAnUnknownState() {
        assertThrows(IllegalArgumentException::class.java) { applyStateUpdate(queued(), "nope", null, null, null, false, T1) }
    }

    @Test
    fun likeEscapesPercentUnderscoreAndBackslash() {
        assertEquals("a\\%b", escapeLike("a%b"))
        assertEquals("a\\_b", escapeLike("a_b"))
        assertEquals("a\\\\b", escapeLike("a\\b"))
        assertEquals("%100\\% \\_x\\\\%", likePattern("100% _x\\"))
    }

    @Test
    fun entityConvertsToARecord() {
        val record = queued().copy(id = 5).toRecord()
        assertEquals(5L, record.id)
        assertEquals("youtube:x", record.videoKey)
        assertEquals(T0, record.createdAt)
        assertNotNull(record.url)
    }
}
