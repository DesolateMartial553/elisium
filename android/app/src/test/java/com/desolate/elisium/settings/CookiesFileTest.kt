package com.desolate.elisium.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private const val HEADER = "# Netscape HTTP Cookie File"

/** Two real-shaped rows: domain, include-subdomains, path, secure, expiry, name, value. */
private val ROWS = """
    .instagram.com	TRUE	/	TRUE	1798761600	sessionid	abc123
    .instagram.com	TRUE	/	FALSE	1798761600	csrftoken	def456
""".trimIndent()

class CookiesFileTest {
    @Test
    fun `a header and rows are a valid file`() {
        val check = checkCookiesFile("$HEADER\n$ROWS\n")
        assertEquals(CookiesCheck.Valid(2), check)
    }

    @Test
    fun `rows without the header are still accepted`() {
        // Browser exports are not always written by the same extension.
        assertEquals(CookiesCheck.Valid(2), checkCookiesFile(ROWS))
    }

    @Test
    fun `the alternative header is accepted`() {
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile("# HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t1\tname\tvalue"))
    }

    @Test
    fun `comments and blank lines do not count`() {
        val text = "$HEADER\n\n# a comment\n$ROWS\n\n#Exported by an extension\n"
        assertEquals(CookiesCheck.Valid(2), checkCookiesFile(text))
    }

    @Test
    fun `a carriage return column does not break a row`() {
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile("$HEADER\r\n.instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\tabc\r\n"))
    }

    @Test
    fun `empty and blank files are empty`() {
        assertEquals(CookiesCheck.Empty, checkCookiesFile(""))
        assertEquals(CookiesCheck.Empty, checkCookiesFile("   \n\n\t  "))
        assertEquals(CookiesCheck.Empty, checkCookiesFile(null))
    }

    @Test
    fun `a header with no cookies is empty not wrong`() {
        assertEquals(CookiesCheck.Empty, checkCookiesFile("$HEADER\n# nothing here\n"))
    }

    @Test
    fun `an html page saved as cookies txt is the wrong format`() {
        val html = "<!DOCTYPE html>\n<html><body><h1>Instagram</h1></body></html>"
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile(html))
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile("   <html></html>"))
    }

    @Test
    fun `json and random text are the wrong format`() {
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile("""{"sessionid": "abc"}"""))
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile("name,value\nsessionid,abc"))
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile("just some words"))
    }

    @Test
    fun `a row needs all seven fields`() {
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile(".instagram.com\tTRUE\t/\tTRUE\t1\tsessionid"))
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile("$HEADER\n.instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\t"))
    }

    @Test
    fun `the include subdomains column must be true or false`() {
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile(".instagram.com\tMAYBE\t/\tTRUE\t1\tsessionid\tabc"))
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile("$HEADER\n.instagram.com\tfalse\t/\tTRUE\t1\tsessionid\tabc"))
    }

    @Test
    fun `a row needs a domain and a name`() {
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile("\tTRUE\t/\tTRUE\t1\tsessionid\tabc"))
        assertEquals(CookiesCheck.WrongFormat, checkCookiesFile(".instagram.com\tTRUE\t/\tTRUE\t1\t\tabc"))
    }

    @Test
    fun `a byte order mark is ignored`() {
        assertEquals(CookiesCheck.Valid(1), checkCookiesFile("\uFEFF$HEADER\n.instagram.com\tTRUE\t/\tTRUE\t1\tsessionid\tabc"))
    }

    @Test
    fun `the constant is the header yt-dlp looks for`() {
        assertTrue(checkCookiesFile("$COOKIES_HEADER\n.instagram.com\tTRUE\t/\tTRUE\t1\tn\tv") is CookiesCheck.Valid)
        assertTrue(checkCookiesFile("$COOKIES_HEADER_ALT\n.instagram.com\tTRUE\t/\tTRUE\t1\tn\tv") is CookiesCheck.Valid)
    }
}
