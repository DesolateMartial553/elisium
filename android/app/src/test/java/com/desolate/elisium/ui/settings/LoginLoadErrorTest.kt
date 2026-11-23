package com.desolate.elisium.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LoginLoadErrorTest {
    @Test
    fun `known error codes get plain words`() {
        assertEquals("could not find Instagram", loginErrorReason(-2, "net::ERR_NAME_NOT_RESOLVED"))
        assertEquals("could not connect", loginErrorReason(-6, "net::ERR_CONNECTION_REFUSED"))
        assertEquals("timed out", loginErrorReason(-8, null))
        assertEquals("secure connection failed", loginErrorReason(-11, ""))
    }

    @Test
    fun `unknown codes use a short cleaned description or the code`() {
        assertEquals("ERR_WEIRD", loginErrorReason(-99, "net::ERR_WEIRD"))
        assertEquals("error -99", loginErrorReason(-99, "  "))
        assertTrue(loginErrorReason(-99, "x".repeat(500)).length <= 60)
        assertFalse("SECRETVALUE" in loginErrorReason(-99, "Cookie: sessionid=SECRETVALUE"))
    }

    @Test
    fun `http statuses`() {
        assertFalse(loginHttpIsFailure(200))
        assertFalse(loginHttpIsFailure(399))
        assertTrue(loginHttpIsFailure(400))
        assertTrue(loginHttpIsFailure(503))
        assertEquals("Instagram says too many requests", loginHttpReason(429))
        assertEquals("Instagram refused the request (HTTP 403)", loginHttpReason(403))
        assertEquals("Instagram had a problem (HTTP 503)", loginHttpReason(503))
        assertEquals("HTTP 400", loginHttpReason(400))
    }
}
