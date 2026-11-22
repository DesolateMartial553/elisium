package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class PresetsTest {
    @Test
    fun `presets table`() {
        assertEquals(
            listOf("best", "1080p", "720p", "audio-mp3", "audio-m4a", "audio-opus", "audio-flac", "smallest"),
            Presets.PRESETS.keys.toList(),
        )
        assertEquals("bestvideo*+bestaudio/best", Presets.PRESETS.getValue("best").formatSelector)
        assertEquals(
            "bestvideo*[height<=1080]+bestaudio/best[height<=1080]",
            Presets.PRESETS.getValue("1080p").formatSelector,
        )
        assertEquals(2, Regex("720").findAll(Presets.PRESETS.getValue("720p").formatSelector).count())
        val mp3 = Presets.PRESETS.getValue("audio-mp3")
        assertEquals("Audio only (MP3)", mp3.label)
        assertEquals("bestaudio/best", mp3.formatSelector)
        assertEquals(listOf("-x", "--audio-format", "mp3"), mp3.extraArgs)
        for (fmt in listOf("m4a", "opus", "flac")) {
            assertEquals(listOf("-x", "--audio-format", fmt), Presets.PRESETS.getValue("audio-$fmt").extraArgs)
        }
        // Audio copy: the stream already in the wanted container is taken as it is (no re-encode).
        assertEquals("bestaudio[ext=m4a]/bestaudio/best", Presets.PRESETS.getValue("audio-m4a").formatSelector)
        assertEquals("bestaudio[acodec=opus]/bestaudio/best", Presets.PRESETS.getValue("audio-opus").formatSelector)
        assertEquals("bestaudio/best", Presets.PRESETS.getValue("audio-flac").formatSelector)
        assertEquals("wv*+wa/w", Presets.PRESETS.getValue("smallest").formatSelector)
        assertEquals("Smallest file", Presets.PRESETS.getValue("smallest").label)
        assertEquals("best", Presets.DEFAULT_ID)
    }

    @Test
    fun `unknown preset falls back to best`() {
        assertSame(Presets.PRESETS.getValue("best"), Presets.get("nope"))
        assertSame(Presets.PRESETS.getValue("best"), Presets.get(null))
        assertEquals("720p", Presets.get("720p").id)
    }
}
