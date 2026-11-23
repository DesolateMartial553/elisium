package com.desolate.elisium.engine

import com.desolate.elisium.media.HttpMediaFetcher
import com.desolate.elisium.media.HttpResult
import com.desolate.elisium.media.MediaEngine
import com.desolate.elisium.media.MediaFailure
import com.desolate.elisium.media.MediaFetchException
import com.desolate.elisium.media.FakeHttp
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

private const val PHOTO_1 = "https://www.instagram.com/p/Df3o9GRCWFQ/"
private const val PHOTO_2 = "https://www.instagram.com/p/Dfwnkbukyc5/"
private const val NO_VIDEO_TEXT = "ERROR: [Instagram] Df3o9GRCWFQ: There is no video in this post"
private const val SECRET = "SESSIONSECRET123456"

@OptIn(ExperimentalCoroutinesApi::class)
private class CRig(scope: CoroutineScope, base: File) {
    val backend = FakeBackend()
    val fetcher = FakeFetcher()
    val downloader = FakeDownloader()
    val queue = DownloadQueue(
        FakeHistory(), Archive(File(base, "data/archive.txt")), FolderStore(), backend, File(base, "staging"), scope,
        delay = { ms -> kotlinx.coroutines.delay(ms) },
    )

    init {
        queue.setMediaEngine(MediaEngine(fetcher, downloader))
    }

    suspend fun runAll() {
        queue.start()
        queue.waitUntilIdle()
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class ErrorCauseTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun TestScope.rig() = CRig(backgroundScope, tmp.root)

    // -- unsigned photo posts end as login_required ------------------------------
    @Test
    fun `unsigned photo post with an engine that fails on missing cookies is login_required`() = runTest {
        val r = rig()
        r.backend.probeHandler = { throw ProbeFailure(NO_VIDEO_TEXT) }
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "no cookies") }
        val a = r.queue.add(PHOTO_1)
        val b = r.queue.add(PHOTO_2)
        r.runAll()
        for (id in listOf(a.id, b.id)) {
            val item = r.queue.item(id)!!
            assertEquals("failed", item.state)
            assertEquals("login_required", item.error!!.code)
            assertEquals("Instagram needs you signed in.", item.error!!.message)
        }
        assertTrue(r.fetcher.cookies.all { it == null })
    }

    @Test
    fun `unsigned photo post answered 401 by Instagram is login_required`() = runTest {
        val r = rig()
        val http = FakeHttp().also { it.onGet = { HttpResult(401, """{"message":"login_required","require_login":true,"status":"fail"}""") } }
        r.queue.setMediaEngine(MediaEngine(HttpMediaFetcher(http), r.downloader))
        r.backend.probeHandler = { throw ProbeFailure(NO_VIDEO_TEXT) }
        val item = r.queue.add(PHOTO_1)
        r.runAll()
        assertEquals("login_required", r.queue.item(item.id)!!.error!!.code)
        assertEquals(1, http.requests.size)
        assertFalse(http.requests[0].second.containsKey("Cookie"))
    }

    @Test
    fun `yt-dlp failing in a way it cannot name still reaches the media engine for a photo post`() = runTest {
        val r = rig()
        r.backend.probeHandler = { throw IllegalStateException("python crashed") } // not a ProbeFailure
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP 401") }
        val item = r.queue.add(PHOTO_1)
        r.runAll()
        assertEquals(listOf(PHOTO_1), r.fetcher.calls.toList())
        assertEquals("login_required", r.queue.item(item.id)!!.error!!.code)
    }

    @Test
    fun `unnamed yt-dlp probe message on a photo post falls through to the media engine`() = runTest {
        val r = rig()
        r.backend.probeHandler = { throw ProbeFailure("ERROR: [Instagram] Df3o9GRCWFQ: something nobody has seen before") }
        r.fetcher.handler = { throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP 401") }
        val item = r.queue.add(PHOTO_1)
        r.runAll()
        assertEquals("login_required", r.queue.item(item.id)!!.error!!.code)
    }

    @Test
    fun `yt-dlp redirected to the login page is login_required`() {
        val info = explain(
            "ERROR: [Instagram] Df3o9GRCWFQ: The webpage request was redirected to the login page. " +
                "You have exceeded the rate-limit for accessing posts anonymously",
            PHOTO_1,
        )
        assertEquals("login_required", info.code)
    }

    // -- unexpected exceptions keep their cause ------------------------------------
    @Test
    fun `a thrown exception ends as unknown with a clean cause`() = runTest {
        val r = rig()
        r.backend.probeHandler = { throw ProbeFailure(NO_VIDEO_TEXT) }
        r.fetcher.handler = {
            throw IllegalStateException("boom Cookie: sessionid=$SECRET; csrftoken=abc123 more words")
        }
        val item = r.queue.add(PHOTO_1)
        r.runAll()
        val error = r.queue.item(item.id)!!.error!!
        assertEquals("unknown", error.code)
        assertEquals("Download failed.", error.message)
        assertTrue(error.fix, error.fix.startsWith("See Details"))
        assertTrue(error.fix, "IllegalStateException" in error.fix)
        assertTrue(error.fix, "boom" in error.fix)
        assertNoCookieText(error.fix)
    }

    @Test
    fun `an unmatched yt-dlp error keeps its last line as the cause`() = runTest {
        val r = rig()
        r.backend.startHandler = { _, _ ->
            FakeHandle().also { it.finish(failureOutcome("[download] Destination: x\nERROR: kaboom with sessionid=$SECRET")) }
        }
        val item = r.queue.add("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        r.runAll()
        val error = r.queue.item(item.id)!!.error!!
        assertEquals("unknown", error.code)
        assertTrue(error.fix, "kaboom" in error.fix)
        assertNoCookieText(error.fix)
    }

    @Test
    fun `a media engine crash on a story link keeps its cause`() = runTest {
        val r = rig()
        r.fetcher.handler = { throw NullPointerException("no value") }
        val item = r.queue.add("https://www.instagram.com/stories/example_user/")
        r.runAll()
        val error = r.queue.item(item.id)!!.error!!
        assertEquals("unknown", error.code)
        assertTrue(error.fix, "NullPointerException: no value" in error.fix)
    }

    // -- the sanitiser itself ---------------------------------------------------------
    @Test
    fun `sanitiser removes cookie and authorization text and truncates`() {
        val cases = listOf(
            "Cookie: sessionid=$SECRET; csrftoken=zzz",
            "set-cookie: sessionid=$SECRET",
            "Authorization: Bearer abcdefghijklmnop.qrstuvwx",
            "bad value sessionid=$SECRET here",
            "csrftoken=ABCDEF and ds_user_id=12345",
            "opaque ${"a1B2".repeat(12)} blob",
            "x\tsessionid\t$SECRET",
        )
        for (text in cases) {
            val clean = sanitizeCause(IllegalArgumentException(text))
            assertTrue(clean, clean.startsWith("IllegalArgumentException:"))
            assertNoCookieText(clean)
            assertFalse(clean, "a1B2a1B2a1B2a1B2a1B2" in clean)
        }
        val long = sanitizeCause(RuntimeException("word ".repeat(200)))
        assertTrue(long.length <= 200)
        assertTrue(long.endsWith("..."))
        assertEquals("RuntimeException:", sanitizeCause(RuntimeException()))
    }

    @Test
    fun `withCause only touches unknown errors`() {
        val login = explain("you need to log in to access this content")
        assertEquals(login, withCause(login, "anything"))
        val unknown = explain("zzz")
        assertEquals("unknown", withCause(unknown, "boom").code)
        assertEquals("See Details: boom", withCause(unknown, "boom").fix)
        assertEquals(unknown, withCause(unknown, "   "))
        assertEquals("last", lastLogLine("first\n\nlast\n  "))
    }

    private fun assertNoCookieText(text: String) {
        val lower = text.lowercase()
        assertFalse(text, SECRET.lowercase() in lower)
        assertFalse(text, "abc123" in lower || "csrftoken=" in lower && "[removed]" !in lower)
        assertFalse(text, "cookie:" in lower)
        assertFalse(text, "sessionid=" in lower && "sessionid=[removed]" !in lower)
        assertFalse(text, "bearer abc" in lower)
    }
}
