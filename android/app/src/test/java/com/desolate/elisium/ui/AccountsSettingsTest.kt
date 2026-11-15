package com.desolate.elisium.ui

import com.desolate.elisium.settings.CookiesCheck
import com.desolate.elisium.settings.CookiesImport
import com.desolate.elisium.settings.CookiesStatus
import com.desolate.elisium.settings.CookiesStore
import com.desolate.elisium.settings.checkCookiesFile
import com.desolate.elisium.ui.settings.SettingsViewModel
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** In-memory [CookiesStore] with the same validation as the real one, minus the file system. */
class FakeCookiesStore(start: CookiesStatus = CookiesStatus.None) : CookiesStore {
    var stored: String? = null
    var current: CookiesStatus = start
    var removed = 0

    override fun status(): CookiesStatus = current

    override fun import(text: String?): CookiesImport {
        val check = checkCookiesFile(text)
        if (check is CookiesCheck.Valid && text != null) {
            stored = text
            current = CookiesStatus.Imported(check.count)
        }
        return CookiesImport(check, current)
    }

    override fun remove(): CookiesStatus {
        removed++
        stored = null
        current = CookiesStatus.None
        return current
    }

    override fun file(): File? = null
}

private const val VALID = "# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\tabc\n"

@OptIn(ExperimentalCoroutinesApi::class)
class AccountsSettingsTest {
    @Test fun anImportedFileShowsItsCookieCount() = runTest(UnconfinedTestDispatcher()) {
        val cookies = FakeCookiesStore()
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = cookies)
        assertEquals(CookiesStatus.None, vm.state.value.cookies)
        vm.importCookies(VALID)
        assertEquals(CookiesStatus.Imported(1), vm.state.value.cookies)
        assertNull(vm.state.value.cookiesRejected)
        assertEquals(VALID, cookies.stored)
    }

    @Test fun anEmptyFileIsRejectedAndNothingIsStored() = runTest(UnconfinedTestDispatcher()) {
        val cookies = FakeCookiesStore()
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = cookies)
        vm.importCookies("")
        assertEquals(CookiesCheck.Empty, vm.state.value.cookiesRejected)
        assertEquals(CookiesStatus.None, vm.state.value.cookies)
        assertNull(cookies.stored)
    }

    @Test fun anHtmlFileIsRejectedAsTheWrongFormat() = runTest(UnconfinedTestDispatcher()) {
        val cookies = FakeCookiesStore()
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = cookies)
        vm.importCookies("<html><body>Instagram</body></html>")
        assertEquals(CookiesCheck.WrongFormat, vm.state.value.cookiesRejected)
        assertEquals(CookiesStatus.None, vm.state.value.cookies)
    }

    @Test fun anUnreadablePickIsRejectedRatherThanCrashing() = runTest(UnconfinedTestDispatcher()) {
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = FakeCookiesStore())
        vm.importCookies(null)
        assertEquals(CookiesCheck.Empty, vm.state.value.cookiesRejected)
    }

    @Test fun removingClearsTheCountAndTheMessage() = runTest(UnconfinedTestDispatcher()) {
        val cookies = FakeCookiesStore(CookiesStatus.Imported(3))
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = cookies)
        assertEquals(CookiesStatus.Imported(3), vm.state.value.cookies)
        vm.importCookies("not a cookie file")
        assertEquals(CookiesCheck.WrongFormat, vm.state.value.cookiesRejected)
        vm.removeCookies()
        assertEquals(CookiesStatus.None, vm.state.value.cookies)
        assertNull(vm.state.value.cookiesRejected)
        assertEquals(1, cookies.removed)
    }

    @Test fun anExistingImportIsShownOnFirstLoad() = runTest(UnconfinedTestDispatcher()) {
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = FakeCookiesStore(CookiesStatus.Imported(4)))
        assertEquals(CookiesStatus.Imported(4), vm.state.value.cookies)
        assertNull(vm.state.value.cookiesRejected)
    }

    @Test fun otherSettingsStillWorkWhenNothingIsImported() = runTest(UnconfinedTestDispatcher()) {
        val store = FakeSettingsStore()
        val vm = SettingsViewModel(store, backgroundScope)
        vm.setWifiOnly(false)
        assertEquals(false, store.state.value.wifiOnly)
        assertEquals(CookiesStatus.None, vm.state.value.cookies)
    }

    @Test fun aCapturedSessionIsStoredLikeAPickedFile() = runTest(UnconfinedTestDispatcher()) {
        // Brief 9B: the in-app sign-in hands the same kind of text to the same store.
        val cookies = FakeCookiesStore()
        val vm = SettingsViewModel(FakeSettingsStore(), backgroundScope, cookies = cookies)
        val session = "# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\tabc\n"
        assertEquals(true, vm.importCookies(session))
        assertEquals(CookiesStatus.Imported(1), vm.state.value.cookies)
        assertNull(vm.state.value.cookiesRejected)
        assertEquals(session, cookies.stored)
        // A session text that is not a cookie file is refused and reported, never stored.
        assertEquals(false, vm.importCookies("sessionid=abc"))
        assertEquals(CookiesCheck.WrongFormat, vm.state.value.cookiesRejected)
    }
}
