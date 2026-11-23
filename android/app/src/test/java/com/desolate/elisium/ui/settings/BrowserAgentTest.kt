package com.desolate.elisium.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class BrowserAgentTest {
    private val webView = "Mozilla/5.0 (Linux; Android 14; RMX3085 Build/UP1A; wv) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.39 Mobile Safari/537.36"

    @Test fun dropsTheWebViewMarkers() {
        val ua = browserLikeUserAgent(webView)
        assertFalse(ua.contains("; wv"))
        assertFalse(ua.contains("Version/4.0"))
        assertEquals(
            "Mozilla/5.0 (Linux; Android 14; RMX3085 Build/UP1A) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/131.0.6778.39 Mobile Safari/537.36",
            ua,
        )
    }

    @Test fun leavesAPlainChromeAgentAlone() {
        val chrome = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36"
        assertEquals(chrome, browserLikeUserAgent(chrome))
    }
}
