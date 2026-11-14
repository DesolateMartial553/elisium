package com.desolate.elisium.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ShareIntakeTest {
    @Test
    fun aBareUrl() {
        assertEquals(listOf("https://youtu.be/dQw4w9WgXcQ"), extractUrls("https://youtu.be/dQw4w9WgXcQ"))
    }

    @Test
    fun urlInsideFreeText() {
        assertEquals(
            listOf("https://youtu.be/dQw4w9WgXcQ?si=abc"),
            extractUrls("Check this out: https://youtu.be/dQw4w9WgXcQ?si=abc it is great"),
        )
    }

    @Test
    fun multipleUrlsKeepOrderAndDropDuplicates() {
        val text = "a https://a.com/1 b http://b.com/2\nhttps://a.com/1"
        assertEquals(listOf("https://a.com/1", "http://b.com/2"), extractUrls(text))
    }

    @Test
    fun trailingPunctuationIsDropped() {
        assertEquals(listOf("https://a.com/x"), extractUrls("see https://a.com/x."))
        assertEquals(listOf("https://a.com/x"), extractUrls("see https://a.com/x, ok"))
        assertEquals(listOf("https://a.com/x"), extractUrls("really? https://a.com/x!?"))
        assertEquals(listOf("https://a.com/x"), extractUrls("\"https://a.com/x\""))
    }

    @Test
    fun closingBracketIsDroppedOnlyWhenUnbalanced() {
        assertEquals(listOf("https://a.com/x"), extractUrls("(see https://a.com/x)"))
        assertEquals(listOf("https://en.wikipedia.org/wiki/Foo_(bar)"), extractUrls("https://en.wikipedia.org/wiki/Foo_(bar)"))
        assertEquals(listOf("https://a.com/x"), extractUrls("[https://a.com/x]"))
    }

    @Test
    fun queryAndFragmentSurvive() {
        assertEquals(
            listOf("https://www.youtube.com/watch?v=abc&t=30s#top"),
            extractUrls("https://www.youtube.com/watch?v=abc&t=30s#top"),
        )
    }

    @Test
    fun schemeIsCaseInsensitiveAndOtherSchemesAreIgnored() {
        assertEquals(listOf("HTTPS://A.COM/X"), extractUrls("HTTPS://A.COM/X"))
        assertTrue(extractUrls("ftp://a.com/x and mailto:me@x.com").isEmpty())
    }

    @Test
    fun noUrlGivesAnEmptyList() {
        assertTrue(extractUrls("just words").isEmpty())
        assertTrue(extractUrls("").isEmpty())
        assertTrue(extractUrls(null).isEmpty())
        assertTrue(extractUrls("https://").isEmpty())
        assertTrue(extractUrls("see https:// here").isEmpty())
    }

    @Test
    fun urlsSeparatedByNewlinesAndAngleBrackets() {
        assertEquals(listOf("https://a.com/1", "https://b.com/2"), extractUrls("<https://a.com/1>\n<https://b.com/2>"))
    }

    @Test
    fun confirmationLine() {
        assertEquals("Added 1 link", shareConfirmation(1, 0, 1))
        assertEquals("Added 3 links", shareConfirmation(3, 0, 3))
        assertEquals("Added 1 link (1 already in the list)", shareConfirmation(1, 1, 2))
        assertEquals("Added 0 links (2 already in the list)", shareConfirmation(0, 2, 2))
        assertEquals("No links found in the shared text", shareConfirmation(0, 0, 0))
    }

    // -- Instagram / TikTok share sheets (brief 8B) --------------------------------------
    @Test
    fun instagramShareTextYieldsTheFirstUrl() {
        val text = "someone on Instagram: \"Dinner again\" https://www.instagram.com/reel/CabcDEF123/?igsh=MTZ0dA== " +
            "Copy this link to share the post."
        assertEquals(listOf("https://www.instagram.com/reel/CabcDEF123/?igsh=MTZ0dA=="), extractUrls(text))
    }

    @Test
    fun tiktokShareTextYieldsTheFirstUrl() {
        val text = "Check out tiktok's video! #TikTok https://www.tiktok.com/@tiktok/video/7106594312292453675?_t=8abc&_r=1"
        val urls = extractUrls(text)
        assertEquals(listOf("https://www.tiktok.com/@tiktok/video/7106594312292453675?_t=8abc&_r=1"), urls)
        assertEquals("the first URL is the one queued", "https://www.tiktok.com/@tiktok/video/7106594312292453675?_t=8abc&_r=1", urls.first())
    }

    @Test
    fun shareTextWithWordsAroundItKeepsOnlyTheLinks() {
        val text = "Look at this: https://www.instagram.com/p/CabcDEF123/ - sent from my phone (Instagram)"
        assertEquals(listOf("https://www.instagram.com/p/CabcDEF123/"), extractUrls(text))
        assertEquals(
            listOf("https://vm.tiktok.com/ZMabc123/"),
            extractUrls("<https://vm.tiktok.com/ZMabc123/>\nshared with Elisium"),
        )
    }
}
