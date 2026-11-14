package com.desolate.elisium.ui

import com.desolate.elisium.ui.permissions.PermissionFacts
import com.desolate.elisium.ui.permissions.PermissionKind
import com.desolate.elisium.ui.permissions.nextPermissionToAsk
import com.desolate.elisium.ui.permissions.rationaleRes
import com.desolate.elisium.ui.permissions.shouldAskNotifications
import com.desolate.elisium.ui.permissions.shouldAskStorage
import com.desolate.elisium.ui.permissions.showNotificationsOffNotice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PermissionRulesTest {
    private fun facts(
        sdk: Int,
        notif: Boolean = false,
        notifAsked: Boolean = false,
        storage: Boolean = false,
        storageAsked: Boolean = false,
    ) = PermissionFacts(sdk, notif, notifAsked, storage, storageAsked)

    @Test fun notificationsOnlyFromApi33AndOnlyOnce() {
        assertFalse(shouldAskNotifications(facts(32)))
        assertTrue(shouldAskNotifications(facts(33)))
        assertTrue(shouldAskNotifications(facts(35)))
        assertFalse(shouldAskNotifications(facts(33, notif = true)))
        assertFalse(shouldAskNotifications(facts(33, notifAsked = true)))
    }

    @Test fun storageOnlyOnApi26To28AndOnlyOnce() {
        assertFalse(shouldAskStorage(facts(25)))
        assertTrue(shouldAskStorage(facts(26)))
        assertTrue(shouldAskStorage(facts(28)))
        assertFalse(shouldAskStorage(facts(29)))
        assertFalse(shouldAskStorage(facts(27, storage = true)))
        assertFalse(shouldAskStorage(facts(27, storageAsked = true)))
    }

    @Test fun nextPermissionPicksTheOneThatApplies() {
        assertEquals(PermissionKind.Storage, nextPermissionToAsk(facts(27)))
        assertEquals(PermissionKind.Notifications, nextPermissionToAsk(facts(34)))
        assertNull(nextPermissionToAsk(facts(30)))
        assertNull(nextPermissionToAsk(facts(34, notifAsked = true)))
        assertNull(nextPermissionToAsk(facts(27, storageAsked = true)))
        assertNull(nextPermissionToAsk(facts(34, notif = true)))
    }

    @Test fun rationaleTextsAreDistinct() {
        assertNotEquals(rationaleRes(PermissionKind.Notifications), rationaleRes(PermissionKind.Storage))
    }

    @Test fun settingsNoticeShowsWhenNotificationsAreOff() {
        assertTrue(showNotificationsOffNotice(false))
        assertFalse(showNotificationsOffNotice(true))
    }
}
