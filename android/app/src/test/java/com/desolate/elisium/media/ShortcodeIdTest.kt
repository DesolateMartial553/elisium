package com.desolate.elisium.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ShortcodeIdTest {
    @Test
    fun `known pair converts both ways`() {
        // Computed independently: 1234567890123456789 in base64-url, no padding.
        assertEquals("1234567890123456789", ShortcodeId.toMediaId("BEiEPR96YEV"))
        assertEquals("BEiEPR96YEV", ShortcodeId.toShortcode("1234567890123456789"))
    }

    @Test
    fun `round trips across the alphabet`() {
        val ids = listOf(
            "1",
            "61",
            "64",
            "65",
            "4095",
            "3111111111111111111",
            "3141592653589793238",
            "9223372036854775807",
            "18446744073709551615",
        )
        for (id in ids) {
            val shortcode = ShortcodeId.toShortcode(id) ?: throw AssertionError("no shortcode for $id")
            assertEquals(id, ShortcodeId.toMediaId(shortcode))
            assertEquals(shortcode, ShortcodeId.toShortcode(id))
        }
    }

    @Test
    fun `zero is a single A`() {
        assertEquals("A", ShortcodeId.toShortcode("0"))
        assertEquals("0", ShortcodeId.toMediaId("A"))
    }

    @Test
    fun `the alphabet uses base64 url characters`() {
        assertEquals("B", ShortcodeId.toShortcode("1"))
        assertEquals("-", ShortcodeId.toShortcode("62"))
        assertEquals("_", ShortcodeId.toShortcode("63"))
    }

    @Test
    fun `invalid input is null`() {
        assertNull(ShortcodeId.toMediaId(""))
        assertNull(ShortcodeId.toMediaId("abc+def"))
        assertNull(ShortcodeId.toMediaId("abc/def"))
        assertNull(ShortcodeId.toMediaId("abc def"))
        assertNull(ShortcodeId.toMediaId("abc.def"))
        assertNull(ShortcodeId.toShortcode(""))
        assertNull(ShortcodeId.toShortcode("12a"))
        assertNull(ShortcodeId.toShortcode("-1"))
        assertNull(ShortcodeId.toShortcode(" 12"))
    }
}
