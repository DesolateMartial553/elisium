package com.desolate.elisium.storage

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OutputNamingTest {
    @Test
    fun relativePathIsDownloadElisiumWithTrailingSlash() {
        assertEquals("Download/Elisium/", RELATIVE_PATH)
    }

    @Test
    fun skipsTheInsertWhenTheSameNameExists() {
        assertEquals(PublishDecision.USE_EXISTING, decidePublish(sameNameExists = true))
        assertEquals(PublishDecision.INSERT, decidePublish(sameNameExists = false))
    }

    @Test
    fun mimeTypesFromTheExtension() {
        assertEquals("video/mp4", mimeTypeFor("A [id].mp4"))
        assertEquals("video/x-matroska", mimeTypeFor("A.mkv"))
        assertEquals("video/webm", mimeTypeFor("A.webm"))
        assertEquals("audio/mpeg", mimeTypeFor("A.mp3"))
        assertEquals("audio/mp4", mimeTypeFor("A.m4a"))
        assertEquals("audio/opus", mimeTypeFor("A.opus"))
        assertEquals("audio/flac", mimeTypeFor("A.flac"))
        assertEquals("image/jpeg", mimeTypeFor("A.JPG"))
    }

    @Test
    fun unknownOrMissingExtensionIsOctetStream() {
        assertEquals("application/octet-stream", mimeTypeFor("A.xyz"))
        assertEquals("application/octet-stream", mimeTypeFor("noext"))
        assertEquals("application/octet-stream", mimeTypeFor("trailing."))
    }

    @Test
    fun safeNameRemovesEachForbiddenCharacter() {
        assertEquals("ab.mp4", safeDisplayName("a/b.mp4"))
        assertEquals("ab.mp4", safeDisplayName("a\\b.mp4"))
        assertEquals("ab.mp4", safeDisplayName("a:b.mp4"))
        assertEquals("ab.mp4", safeDisplayName("a\u0000b\u001f.mp4"))
        assertEquals("ab.mp4", safeDisplayName("a\nb\u007f.mp4"))
    }

    @Test
    fun safeNameLeavesATemplateNameUnchanged() {
        val name = "Rick Astley - Never Gonna Give You Up [dQw4w9WgXcQ].mp4"
        assertEquals(name, safeDisplayName(name))
    }

    @Test
    fun safeNameKeepsUnicode() {
        val name = "日本語のタイトル [abc123].webm"
        assertEquals(name, safeDisplayName(name))
    }

    @Test
    fun safeNameDropsLeadingDotsAndWhitespace() {
        assertEquals("hidden.mp4", safeDisplayName("  ..hidden.mp4 "))
    }

    @Test
    fun emptyNameBecomesDownload() {
        assertEquals("download", safeDisplayName(""))
        assertEquals("download", safeDisplayName("///:::"))
        assertEquals("download", safeDisplayName("..."))
    }

    @Test
    fun longTitleIsCutTo150BytesButKeepsIdAndExtension() {
        val name = "a".repeat(300) + " [dQw4w9WgXcQ].mp4"
        val safe = safeDisplayName(name)
        assertEquals("a".repeat(150) + " [dQw4w9WgXcQ].mp4", safe)
    }

    @Test
    fun truncationNeverSplitsACharacter() {
        val title = "é".repeat(100) // 2 bytes each = 200 bytes
        val safe = safeDisplayName("$title [id].mp4")
        val cut = safe.removeSuffix(" [id].mp4")
        assertEquals(75, cut.length)
        assertTrue(cut.toByteArray(Charsets.UTF_8).size <= TITLE_MAX_BYTES)
        assertTrue(safe.endsWith(" [id].mp4"))
    }

    @Test
    fun truncateUtf8Basics() {
        assertEquals("abc", truncateUtf8("abc", 10))
        assertEquals("ab", truncateUtf8("abc", 2))
        assertEquals("a", truncateUtf8("aé", 2)) // the 2-byte char would overflow
        assertEquals("", truncateUtf8("😀", 3)) // 4-byte emoji does not fit in 3
        assertEquals("😀", truncateUtf8("😀x", 4))
    }

    @Test
    fun nameWithoutAnIdSuffixIsStillLimited() {
        val safe = safeDisplayName("b".repeat(400) + ".mp3")
        assertEquals("b".repeat(150) + ".mp3", safe)
    }

    @Test
    fun videoIdMatchingIgnoresUnfinishedFiles() {
        assertTrue(nameHasVideoId("T [dQw4w9WgXcQ].mp4", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T [dQw4w9WgXcQ].mp4.part", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T [dQw4w9WgXcQ].ytdl", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T [dQw4w9WgXcQ].mp4.elisium-tmp", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T dQw4w9WgXcQ.mp4", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T [other].mp4", "dQw4w9WgXcQ"))
        assertFalse(nameHasVideoId("T [].mp4", ""))
    }

    @Test
    fun likeEscapingProtectsWildcards() {
        assertEquals("a\\%b\\_c\\\\d", escapeLike("a%b_c\\d"))
    }

    @Test
    fun likePatternWrapsTheBracketedId() {
        assertEquals("%[abc]%", likePatternForVideoId("abc"))
        assertEquals("%[a\\_b\\%]%", likePatternForVideoId("a_b%"))
    }
}
