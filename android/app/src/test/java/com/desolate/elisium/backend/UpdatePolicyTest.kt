package com.desolate.elisium.backend

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdatePolicyTest {
    private val day = AUTO_UPDATE_INTERVAL_MS
    private val last = 1_000_000_000L

    private fun due(now: Long, lastCheck: Long = last, wifiOnly: Boolean = false, onWifi: Boolean = true, active: Boolean = false) =
        shouldAutoUpdate(now, lastCheck, wifiOnly, onWifi, active)

    @Test fun intervalIsTwentyFourHours() = assertTrue(day == 86_400_000L)

    @Test fun exactlyTwentyFourHoursIsDue() = assertTrue(due(last + day))
    @Test fun oneMillisecondShortIsNotDue() = assertFalse(due(last + day - 1))
    @Test fun justOverIsDue() = assertTrue(due(last + day + 1))
    @Test fun neverCheckedIsDueEvenSoonAfterEpoch() = assertTrue(due(now = 5, lastCheck = 0))
    @Test fun negativeStoredValueCountsAsNeverChecked() = assertTrue(due(now = 5, lastCheck = -3))

    @Test fun wifiOnlyOnCellularBlocks() = assertFalse(due(last + day, wifiOnly = true, onWifi = false))
    @Test fun wifiOnlyOnWifiAllows() = assertTrue(due(last + day, wifiOnly = true, onWifi = true))
    @Test fun wifiOnlyOffAllowsOnCellular() = assertTrue(due(last + day, wifiOnly = false, onWifi = false))

    @Test fun activeDownloadsBlockEvenWhenNeverChecked() {
        assertFalse(due(last + day, active = true))
        assertFalse(due(last + day, lastCheck = 0, active = true))
    }

    @Test fun clockGoingBackwardsDoesNotUpdate() {
        assertFalse(due(now = last - 1))
        assertFalse(due(now = last - 10 * day))
    }
}
