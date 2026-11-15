package com.desolate.elisium.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The pure half of the in-app Instagram sign-in (brief 9B). No network, no Android. */
class InstagramSessionTest {

    // -- parseCookieHeader ----------------------------------------------------------------
    @Test
    fun `an empty header holds no cookies`() {
        assertEquals(emptyList<Pair<String, String>>(), parseCookieHeader(null))
        assertEquals(emptyList<Pair<String, String>>(), parseCookieHeader(""))
        assertEquals(emptyList<Pair<String, String>>(), parseCookieHeader("   "))
        assertEquals(emptyList<Pair<String, String>>(), parseCookieHeader("; ;"))
    }

    @Test
    fun `entries without an equals sign are ignored`() {
        assertEquals(emptyList<Pair<String, String>>(), parseCookieHeader("csrftoken"))
        assertEquals(
            listOf("csrftoken" to "abc"),
            parseCookieHeader("junk; csrftoken=abc; also-junk"),
        )
    }

    @Test
    fun `an equals sign inside a value is kept`() {
        assertEquals(listOf("sessionid" to "a=b=c"), parseCookieHeader("sessionid=a=b=c"))
        assertEquals(
            listOf("csrftoken" to "x", "sessionid" to "ab=="),
            parseCookieHeader("csrftoken=x; sessionid=ab=="),
        )
    }

    @Test
    fun `extra spaces around the entries are trimmed`() {
        assertEquals(
            listOf("csrftoken" to "1", "sessionid" to "2"),
            parseCookieHeader("  csrftoken = 1 ;   sessionid =  2  ;  "),
        )
    }

    @Test
    fun `an entry with no name is ignored`() {
        assertEquals(listOf("ok" to "1"), parseCookieHeader("=nameless; ok=1"))
    }

    @Test
    fun `an empty value is kept as an empty value`() {
        assertEquals(listOf("sessionid" to ""), parseCookieHeader("sessionid="))
    }

    // -- hasInstagramSession --------------------------------------------------------------
    @Test
    fun `a session needs a sessionid cookie with a value`() {
        assertFalse(hasInstagramSession(null))
        assertFalse(hasInstagramSession(""))
        assertFalse(hasInstagramSession("csrftoken=abc; mid=xyz"))
        assertFalse(hasInstagramSession("sessionid="))
        assertFalse(hasInstagramSession("sessionid=   "))
        assertTrue(hasInstagramSession("sessionid=abc123"))
        assertTrue(hasInstagramSession("csrftoken=abc; ds_user_id=42; sessionid=abc123; mid=xyz"))
    }

    // -- toNetscape -----------------------------------------------------------------------
    private val header = "csrftoken=abc; ds_user_id=42; sessionid=IGsession=="
    private val now = 1_700_000_000L

    @Test
    fun `the file starts with the Netscape header`() {
        val text = toNetscape(header, now)
        assertEquals("# Netscape HTTP Cookie File", text.lineSequence().first())
        assertTrue(text.endsWith("\n"))
    }

    @Test
    fun `each cookie becomes a seven field row for instagram`() {
        val rows = toNetscape(header, now).lineSequence()
            .filter { it.isNotEmpty() && !it.startsWith("#") }
            .toList()
        assertEquals(3, rows.size)
        for (row in rows) {
            val f = row.split('\t')
            assertEquals(7, f.size)
            assertEquals(".instagram.com", f[0])
            assertEquals("TRUE", f[1])
            assertEquals("/", f[2])
            assertEquals("TRUE", f[3])
        }
        assertEquals((now + 31_536_000L).toString(), rows[0].split('\t')[4])
        assertEquals("csrftoken", rows[0].split('\t')[5])
        assertEquals("abc", rows[0].split('\t')[6])
        assertEquals("sessionid", rows[2].split('\t')[5])
        assertEquals("IGsession==", rows[2].split('\t')[6]) // the "=" inside a value survives
    }

    @Test
    fun `the expiry is one year after now`() {
        val fields = toNetscape("a=1", 0L).lineSequence().last { it.isNotEmpty() }.split('\t')
        assertEquals("31536000", fields[4])
        val later = toNetscape("a=1", 2_000_000_000L).lineSequence().last { it.isNotEmpty() }.split('\t')
        assertEquals("2031536000", later[4])
    }

    @Test
    fun `the output is a valid cookie file for the engine`() {
        val check = checkCookiesFile(toNetscape(header, now))
        assertEquals(CookiesCheck.Valid(3), check)
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile(toNetscape("sessionid=x", now)))
    }

    @Test
    fun `a header without cookies is only the header line`() {
        assertEquals("# Netscape HTTP Cookie File\n", toNetscape("", now))
        assertEquals(CookiesCheck.Empty, checkCookiesFile(toNetscape("", now)))
    }

    @Test
    fun `a hostile name or value cannot break the row`() {
        val text = toNetscape("a=1; bad\tname=x; other=va\tlue; nl=va\nlue; cr=va\rlue; sessionid=ok", now)
        val rows = text.lineSequence().filter { it.isNotEmpty() && !it.startsWith("#") }.toList()
        assertEquals(listOf("a", "sessionid"), rows.map { it.split('\t')[5] })
        for (row in rows) assertEquals(7, row.split('\t').size)
        assertEquals(CookiesCheck.Valid(2), checkCookiesFile(text))
        // Nothing leaked onto its own line: only the header plus the two good rows.
        assertEquals(3, text.trimEnd('\n').lineSequence().count())
    }

    @Test
    fun `a session value with a tab is dropped rather than written`() {
        val text = toNetscape("sessionid=abc\tdef", now)
        assertEquals(CookiesCheck.Empty, checkCookiesFile(text))
        assertFalse(text.contains("abc"))
    }

    // -- loginHostAllowed (navigation guard) ---------------------------------------------
    @Test
    fun `instagram and facebook hosts are allowed over https`() {
        assertTrue(loginHostAllowed("https://www.instagram.com/accounts/login/"))
        assertTrue(loginHostAllowed("https://instagram.com/accounts/login/?next=%2F"))
        assertTrue(loginHostAllowed("https://m.facebook.com/dialog/oauth?x=1"))
        assertTrue(loginHostAllowed("https://static.fbcdn.net/rsrc/x.js"))
        assertTrue(loginHostAllowed("https://IG.Instagram.com/"))
    }

    @Test
    fun `anything else is blocked`() {
        assertFalse(loginHostAllowed(null))
        assertFalse(loginHostAllowed(""))
        assertFalse(loginHostAllowed("   "))
        assertFalse(loginHostAllowed("http://www.instagram.com/accounts/login/"))
        assertFalse(loginHostAllowed("javascript:alert(1)"))
        assertFalse(loginHostAllowed("intent://scan/#Intent;scheme=zxing;end"))
        assertFalse(loginHostAllowed("https://evil.example.com/"))
        assertFalse(loginHostAllowed("https://instagram.com.evil.example/"))
        assertFalse(loginHostAllowed("https://evilinstagram.com/"))
        assertFalse(loginHostAllowed("https://facebook.com.example.org/"))
        assertFalse(loginHostAllowed("content://com.android.providers/x"))
    }
}
