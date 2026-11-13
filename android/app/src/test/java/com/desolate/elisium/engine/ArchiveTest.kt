package com.desolate.elisium.engine

import java.io.File
import java.io.IOException
import java.nio.file.Path
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ArchiveTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val id = "dQw4w9WgXcQ"

    private fun makeArchive(): Archive = Archive(File(tmp.root, "archive.txt"))
    private fun exists(dir: File): (String, String) -> Boolean = { _, videoId -> fileExistsFor(dir, videoId) }
    private fun outDir(): File = File(tmp.root, "out").also { it.mkdirs() }
    private fun names(): List<String> = tmp.root.list()!!.sorted()

    private fun expectIllegal(block: () -> Unit) {
        try {
            block()
            fail("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }

    // -- round trip ---------------------------------------------------------
    @Test
    fun `add has remove round trip`() {
        val archive = makeArchive()
        assertFalse(archive.has("youtube", id))
        assertTrue(archive.add("youtube", id))
        assertTrue(archive.has("youtube", id))
        assertTrue(archive.remove("youtube", id))
        assertFalse(archive.has("youtube", id))
        assertFalse(archive.remove("youtube", id))
    }

    @Test
    fun `entries survive a new instance`() {
        makeArchive().add("youtube", id)
        assertTrue(Archive(File(tmp.root, "archive.txt")).has("youtube", id))
    }

    @Test
    fun `add is idempotent and writes one line`() {
        val archive = makeArchive()
        assertTrue(archive.add("youtube", id))
        assertFalse(archive.add("youtube", id))
        assertEquals("youtube $id\n", archive.file.readText())
    }

    @Test
    fun `other entries are kept`() {
        val archive = makeArchive()
        archive.add("youtube", "aaa")
        archive.add("vimeo", "12345")
        archive.add("youtube", "bbb")
        assertTrue(archive.remove("vimeo", "12345"))
        assertEquals("youtube aaa\nyoutube bbb\n", archive.file.readText())
    }

    // -- yt-dlp compatible file format -------------------------------------
    @Test
    fun `file format matches yt-dlp`() {
        val archive = makeArchive()
        archive.add("YouTube", "AbC_-123")
        archive.add("vimeo", "98765")
        assertArrayEquals("youtube AbC_-123\nvimeo 98765\n".toByteArray(), archive.file.readBytes())
    }

    @Test
    fun `extractor is lowercased on read and write`() {
        val file = File(tmp.root, "archive.txt")
        file.writeText("YouTube abc123\n")
        val archive = Archive(file)
        assertTrue(archive.has("YouTube", "abc123"))
        assertTrue(archive.has("youtube", "abc123"))
        archive.add("VIMEO", "xyz")
        assertEquals("youtube abc123\nvimeo xyz\n", file.readText())
    }

    @Test
    fun `yt-dlp style file is read as is`() {
        val file = File(tmp.root, "archive.txt")
        file.writeText("youtube dQw4w9WgXcQ\nvimeo 12345\nsoundcloud 99/track-name\n")
        val archive = Archive(file)
        assertTrue(archive.has("youtube", id))
        assertTrue(archive.has("vimeo", "12345"))
        assertTrue(archive.has("soundcloud", "99/track-name"))
        assertFalse(archive.has("youtube", "12345"))
    }

    // -- tolerance -----------------------------------------------------------
    @Test
    fun `missing file is tolerated and not created`() {
        val archive = makeArchive()
        assertFalse(archive.has("youtube", id))
        assertFalse(archive.remove("youtube", id))
        assertFalse(archive.file.exists())
    }

    @Test
    fun `blank and malformed lines are ignored`() {
        val file = File(tmp.root, "archive.txt")
        file.writeText(
            "\n" +
                "   \n" +
                "youtube dQw4w9WgXcQ\n" +
                "\n" +
                "onlyonefield\n" +
                "too many fields here\n" +
                "# yt-dlp does not write comments, but do not choke on one\n" +
                "vimeo 12345\n" +
                "youtube dQw4w9WgXcQ\n",
        )
        val archive = Archive(file)
        assertTrue(archive.has("youtube", id))
        assertTrue(archive.has("vimeo", "12345"))
        assertFalse(archive.has("onlyonefield", "anything"))
        archive.add("youtube", "new")
        assertEquals("youtube dQw4w9WgXcQ\nvimeo 12345\nyoutube new\n", file.readText())
    }

    @Test
    fun `crlf file is tolerated`() {
        val file = File(tmp.root, "archive.txt")
        file.writeBytes("youtube dQw4w9WgXcQ\r\nvimeo 12345\r\n".toByteArray())
        val archive = Archive(file)
        assertTrue(archive.has("youtube", id))
        assertTrue(archive.has("vimeo", "12345"))
    }

    @Test
    fun `absolute path works`() {
        val file = File(tmp.root, "archive.txt")
        Archive(File(file.absolutePath)).add("youtube", id)
        assertTrue(Archive(file).has("youtube", id))
    }

    @Test
    fun `empty fields raise`() {
        val archive = makeArchive()
        for ((extractor, videoId) in listOf("" to "abc", "youtube" to "", "  " to "abc", "youtube" to "   ")) {
            expectIllegal { archive.add(extractor, videoId) }
        }
    }

    @Test
    fun `fields with whitespace raise`() {
        val archive = makeArchive()
        expectIllegal { archive.add("you tube", id) }
        expectIllegal { archive.add("youtube", "abc 123") }
    }

    @Test
    fun `missing parent directory is created`() {
        val archive = Archive(File(tmp.root, "nested/deeper/archive.txt"))
        assertTrue(archive.add("youtube", id))
        assertTrue(archive.has("youtube", id))
    }

    // -- atomic writes -------------------------------------------------------
    @Test
    fun `write leaves no temp files behind`() {
        val archive = makeArchive()
        archive.add("youtube", "aaa")
        archive.add("youtube", "bbb")
        archive.remove("youtube", "aaa")
        assertEquals(listOf("archive.txt"), names())
    }

    @Test
    fun `failed move keeps the old file`() {
        val file = File(tmp.root, "archive.txt")
        var fail = false
        val archive = object : Archive(file) {
            override fun atomicMove(source: Path, target: Path) {
                if (fail) throw IOException("disk full")
                super.atomicMove(source, target)
            }
        }
        archive.add("youtube", "aaa")
        val before = file.readBytes()
        fail = true
        try {
            archive.add("youtube", "bbb")
            fail("expected IOException")
        } catch (_: IOException) {
        }
        assertArrayEquals(before, file.readBytes())
        assertEquals(listOf("archive.txt"), names())
    }

    @Test
    fun `concurrent adds from many threads lose nothing`() {
        val archive = makeArchive()
        val threads = (0 until 8).map { t ->
            Thread { for (i in 0 until 10) archive.add("youtube", "t${t}i$i") }
        }
        threads.forEach { it.start() }
        threads.forEach { it.join() }
        for (t in 0 until 8) for (i in 0 until 10) assertTrue(archive.has("youtube", "t${t}i$i"))
        assertEquals(80, archive.file.readLines().size)
    }

    // -- reconcile -------------------------------------------------------------
    @Test
    fun `reconcile true when archived and file exists`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        File(out, "Some video [$id].mp4").writeBytes(byteArrayOf(1))
        assertTrue(reconcile(archive, "youtube:$id", exists(out)))
        assertTrue(archive.has("youtube", id))
    }

    @Test
    fun `reconcile accepts any extension`() {
        for (filename in listOf("Some video [$id].mp4", "Some video [$id].webm", "Audio [$id].mp3", "  [$id]  ")) {
            val archive = Archive(File(tmp.newFolder(), "archive.txt"))
            val out = tmp.newFolder()
            archive.add("youtube", id)
            File(out, filename).writeBytes(byteArrayOf(1))
            assertTrue(filename, reconcile(archive, "youtube:$id", exists(out)))
        }
    }

    @Test
    fun `reconcile removes stale id when no file`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        archive.add("vimeo", "12345")
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
        assertFalse(archive.has("youtube", id))
        assertTrue(archive.has("vimeo", "12345"))
    }

    @Test
    fun `reconcile deleted file case`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        val file = File(out, "Some video [$id].mp4")
        file.writeBytes(byteArrayOf(1))
        assertTrue(reconcile(archive, "youtube:$id", exists(out)))
        file.delete()
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
        assertFalse(archive.has("youtube", id))
    }

    @Test
    fun `reconcile false when not archived`() {
        val archive = makeArchive()
        val out = outDir()
        File(out, "Some video [$id].mp4").writeBytes(byteArrayOf(1))
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
        assertFalse(archive.file.exists())
    }

    @Test
    fun `reconcile ignores a loose id in another name`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        File(out, "Some video [x$id].mp4").writeBytes(byteArrayOf(1))
        File(out, "Some video $id.mp4").writeBytes(byteArrayOf(1))
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
    }

    @Test
    fun `reconcile part files are not enough`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        File(out, "Some video [$id].mp4.part").writeBytes(byteArrayOf(1))
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
    }

    @Test
    fun `reconcile ignores a directory named like the file`() {
        val archive = makeArchive()
        val out = outDir()
        archive.add("youtube", id)
        File(out, "Some video [$id]").mkdir()
        assertFalse(reconcile(archive, "youtube:$id", exists(out)))
    }

    @Test
    fun `reconcile missing output dir removes the id`() {
        val archive = makeArchive()
        archive.add("youtube", id)
        assertFalse(reconcile(archive, "youtube:$id", exists(File(tmp.root, "nope"))))
        assertFalse(archive.has("youtube", id))
    }

    @Test
    fun `reconcile malformed key is false`() {
        for (key in listOf("", "   ", "youtube", ":abc", "youtube:", "nocolon")) {
            val archive = Archive(File(tmp.newFolder(), "archive.txt"))
            archive.add("youtube", id)
            assertFalse(key, reconcile(archive, key, exists(tmp.root)))
            assertTrue(archive.has("youtube", id))
        }
    }

    @Test
    fun `reconcile passes extractor and id to the output check`() {
        val archive = makeArchive()
        archive.add("generic", "clip")
        val seen = mutableListOf<Pair<String, String>>()
        assertTrue(reconcile(archive, "Generic:clip") { x, v -> seen.add(x to v); true })
        assertEquals(listOf("generic" to "clip"), seen)
    }
}
