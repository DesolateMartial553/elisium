package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProbeDisplayTest {
    @Test
    fun `thumbnail is the probe's link, else the last thumbnail, http(s) only`() {
        assertEquals("https://i.example.com/a.jpg", thumbnailFrom(json("""{"thumbnail": " https://i.example.com/a.jpg "}""")))
        assertEquals(
            "https://i.example.com/big.jpg",
            thumbnailFrom(json("""{"thumbnails": [{"url": "https://i.example.com/small.jpg"}, {"url": "https://i.example.com/big.jpg"}, {"id": "x"}]}""")),
        )
        assertNull(thumbnailFrom(json("""{"thumbnail": "file:///etc/passwd"}""")))
        assertNull(thumbnailFrom(json("""{"thumbnail": "javascript:alert(1)"}""")))
        assertNull(thumbnailFrom(json("""{"thumbnail": 5}""")))
        assertNull(thumbnailFrom(json("{}")))
    }

    @Test
    fun `format label is quality and container, or the audio format`() {
        assertEquals("1080p MP4", formatLabelFrom(json("""{"ext": "mp4", "height": 1080}"""), emptyList()))
        assertEquals("WEBM", formatLabelFrom(json("""{"ext": "webm"}"""), emptyList()))
        assertEquals("720p", formatLabelFrom(json("""{"height": 720}"""), emptyList()))
        assertNull(formatLabelFrom(json("{}"), emptyList()))
        assertNull(formatLabelFrom(json("""{"height": "tall"}"""), emptyList()))
        assertEquals("MP3 audio", formatLabelFrom(json("{}"), listOf("-x", "--audio-format", "mp3")))
        assertEquals("Audio", formatLabelFrom(json("{}"), listOf("-x")))
        assertEquals("Audio", formatLabelFrom(json("{}"), listOf("--extract-audio", "--audio-format")))
    }
}
