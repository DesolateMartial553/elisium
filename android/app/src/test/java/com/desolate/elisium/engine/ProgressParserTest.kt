package com.desolate.elisium.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/** Ports of the pure progress cases in `test_runner.py`. */
class ProgressParserTest {
    @Test
    fun `parse download progress line`() {
        val p = parseProgressLine(
            "[download] {\"status\": \"downloading\", \"downloaded_bytes\": 512," +
                " \"total_bytes\": 1024, \"speed\": 256.5, \"eta\": 2}",
        )
        assertNotNull(p)
        p!!
        assertEquals("downloading", p.stage)
        assertEquals(512L, p.downloadedBytes)
        assertEquals(1024L, p.totalBytes)
        assertEquals(256.5, p.speed!!, 0.0)
        assertEquals(2.0, p.eta!!, 0.0)
        assertEquals(50.0, p.percent!!, 0.0)
    }

    @Test
    fun `parse bare json line without prefix`() {
        assertEquals("downloading", parseProgressLine("{\"status\": \"downloading\", \"downloaded_bytes\": 1}")!!.stage)
    }

    @Test
    fun `parse ignores plain text and ansi`() {
        assertNull(parseProgressLine("[download] Destination: a.mp4"))
        assertNull(parseProgressLine(""))
        assertNull(parseProgressLine("\u001b[0;94m[download]\u001b[0m nothing to see"))
        assertNull(parseProgressLine("{\"status\": \"weird\"}"))
    }

    @Test
    fun `parse uses total bytes estimate`() {
        val p = parseProgressLine("{\"status\": \"downloading\", \"downloaded_bytes\": 50, \"total_bytes_estimate\": 200}")
        assertEquals(25.0, p!!.percent!!, 0.0)
    }

    @Test
    fun `parse finished download is 100 percent`() {
        assertEquals(100.0, parseProgressLine("{\"status\": \"finished\", \"downloaded_bytes\": 9}")!!.percent!!, 0.0)
    }

    @Test
    fun `parse merger postprocess maps to merging`() {
        val p = parseProgressLine("[postprocess] {\"status\": \"started\", \"postprocessor\": \"Merger\"}")!!
        assertEquals("merging", p.stage)
        assertEquals("Merger", p.postprocessor)
    }

    @Test
    fun `parse audio extract maps to converting`() {
        assertEquals(
            "converting",
            parseProgressLine("{\"status\": \"processing\", \"postprocessor\": \"ExtractAudio\"}")!!.stage,
        )
    }

    @Test
    fun `stage for postprocessor names`() {
        assertEquals("merging", stageForPostprocessor("Merger"))
        assertEquals("merging", stageForPostprocessor("FFmpegMerger"))
        assertEquals("converting", stageForPostprocessor("VideoConvertor"))
        assertEquals("converting", stageForPostprocessor("FixupM4a"))
        assertEquals("converting", stageForPostprocessor(""))
    }

    @Test
    fun `housekeeping postprocessors are not converting`() {
        for (name in listOf("MoveFiles", "Metadata", "FFmpegMetadata", "SponsorBlock")) {
            assertEquals(name, "downloading", stageForPostprocessor(name))
        }
    }

    @Test
    fun `real conversion postprocessors stay converting`() {
        for (name in listOf(
            "ExtractAudio", "VideoConvertor", "VideoRemuxer", "EmbedSubtitle", "EmbedThumbnail",
            "ModifyChapters", "FixupM4a",
        )) {
            assertEquals(name, "converting", stageForPostprocessor(name))
        }
    }
}
