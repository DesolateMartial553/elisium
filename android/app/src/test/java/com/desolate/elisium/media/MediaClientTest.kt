package com.desolate.elisium.media

import java.io.File
import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** A scripted network: no real sockets. */
class FakeHttp : HttpTransport {
    val requests = ArrayList<Pair<String, Map<String, String>>>()
    var onGet: (String) -> HttpResult = { HttpResult(404, "") }
    var onDownload: (String, File) -> Int = { _, part -> part.writeText("data"); 200 }
    var ioError: IOException? = null

    override fun get(url: String, headers: Map<String, String>, token: CancelToken): HttpResult {
        requests.add(url to headers)
        ioError?.let { throw it }
        return onGet(url)
    }

    override fun download(url: String, headers: Map<String, String>, part: File, token: CancelToken): Int {
        requests.add(url to headers)
        ioError?.let { throw it }
        return onDownload(url, part)
    }
}

class MediaClientTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun fixture(name: String): String =
        checkNotNull(javaClass.getResourceAsStream("/media/$name")) { "missing fixture $name" }
            .bufferedReader().use { it.readText() }

    private val secret = "SESSION-SECRET-VALUE-123"

    private fun cookies(): File {
        val file = File(tmp.root, "cookies.txt")
        file.writeText(
            "# Netscape HTTP Cookie File\n" +
                ".instagram.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\t$secret\n" +
                "#HttpOnly_.instagram.com\tTRUE\t/\tTRUE\t1893456000\tcsrftoken\tCSRF123\n" +
                ".example.org\tTRUE\t/\tTRUE\t1893456000\tother\tnope\n",
        )
        return file
    }

    private fun fetcher(http: FakeHttp) = HttpMediaFetcher(http)

    private fun failure(block: () -> Unit): MediaFetchException {
        try {
            block()
        } catch (e: MediaFetchException) {
            return e
        }
        fail("expected MediaFetchException")
        throw AssertionError()
    }

    private val token = CancelToken()

    // -- Instagram posts ----------------------------------------------------
    @Test
    fun `a post link asks the media info endpoint with the numeric id and the session`() {
        val http = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_carousel_mixed.json")) } }
        val posts = fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/?igsh=abc", cookies(), token)
        val (url, headers) = http.requests.single()
        assertEquals("https://www.instagram.com/api/v1/media/1234567890123456789/info/", url)
        assertEquals("936619743392459", headers["X-IG-App-ID"])
        assertEquals("CSRF123", headers["X-CSRFToken"])
        assertTrue(headers.getValue("Cookie").contains("sessionid=$secret"))
        assertFalse("other" in headers.getValue("Cookie"))
        assertTrue(headers.getValue("User-Agent").startsWith("Mozilla/5.0"))
        val post = posts.single()
        assertEquals("CmadeUp0003", post.id)
        assertEquals(3, post.items.size)
    }

    @Test
    fun `without cookies there is no Cookie header`() {
        val http = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_single_image.json")) } }
        fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token)
        assertNull(http.requests.single().second["Cookie"])
    }

    @Test
    fun `a photo post with a song keeps the music clip`() {
        val http = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_image_with_music.json")) } }
        val post = fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token).single()
        assertEquals(15400L, post.music?.startMs)
        assertEquals(15000L, post.music?.durationMs)
    }

    @Test
    fun `an empty post is no_media and a login wall is login_required`() {
        val empty = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_empty.json")) } }
        assertEquals(MediaFailure.NO_MEDIA, failure { fetcher(empty).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token) }.failure)
        val wall = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_login_required.json")) } }
        assertEquals(MediaFailure.LOGIN_REQUIRED, failure { fetcher(wall).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token) }.failure)
        val garbage = FakeHttp().apply { onGet = { HttpResult(200, fixture("instagram_malformed.json")) } }
        assertEquals(MediaFailure.UNKNOWN, failure { fetcher(garbage).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token) }.failure)
    }

    @Test
    fun `http statuses map to failures`() {
        fun codeFor(code: Int, body: String = ""): MediaFailure {
            val http = FakeHttp().apply { onGet = { HttpResult(code, body) } }
            return failure { fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token) }.failure
        }
        assertEquals(MediaFailure.RATE_LIMITED, codeFor(429))
        assertEquals(MediaFailure.LOGIN_REQUIRED, codeFor(401))
        assertEquals(MediaFailure.LOGIN_REQUIRED, codeFor(403))
        assertEquals(MediaFailure.NOT_FOUND, codeFor(404))
        assertEquals(MediaFailure.LOGIN_REQUIRED, codeFor(400, """{"message":"login_required"}"""))
        assertEquals(MediaFailure.RATE_LIMITED, codeFor(400, """{"message":"Please wait a few minutes before you try again."}"""))
        assertEquals(MediaFailure.UNKNOWN, codeFor(400, "{}"))
        assertEquals(MediaFailure.NETWORK, codeFor(503))
        assertEquals(MediaFailure.UNKNOWN, codeFor(418))
        assertEquals(MediaFailure.RATE_LIMITED, codeFor(200, """{"message":"Please wait a few minutes","status":"fail"}"""))
    }

    @Test
    fun `a caption that says please wait a few minutes is still a post`() {
        val body = fixture("instagram_single_image.json").replace("A made-up caption for tests", "Please wait a few minutes, more soon")
        val http = FakeHttp().apply { onGet = { HttpResult(200, body) } }
        val post = fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", null, token).single()
        assertEquals("Please wait a few minutes, more soon", post.caption)
    }

    @Test
    fun `an io error is a network failure and never mentions the cookies`() {
        val http = FakeHttp().apply { ioError = IOException("reset $secret") }
        val e = failure { fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", cookies(), token) }
        assertEquals(MediaFailure.NETWORK, e.failure)
        assertFalse(secret in (e.message ?: "") || secret in e.raw)
    }

    @Test
    fun `no failure text ever carries the session`() {
        for (code in listOf(400, 401, 403, 404, 429, 500)) {
            val http = FakeHttp().apply { onGet = { HttpResult(code, "") } }
            val e = failure { fetcher(http).fetch("https://www.instagram.com/p/BEiEPR96YEV/", cookies(), token) }
            assertFalse(secret in e.raw)
            assertFalse("CSRF123" in e.raw)
        }
    }

    @Test
    fun `a link that is not a photo or story link is refused`() {
        val e = failure { fetcher(FakeHttp()).fetch("https://www.instagram.com/reel/AbC/", null, token) }
        assertEquals(MediaFailure.NO_MEDIA, e.failure)
    }

    // -- stories --------------------------------------------------------------
    private fun trayHttp(profile: String, tray: String) = FakeHttp().apply {
        onGet = { url ->
            when {
                "web_profile_info" in url -> HttpResult(200, profile)
                "reels_media" in url -> HttpResult(200, tray)
                else -> HttpResult(404, "")
            }
        }
    }

    private val profile = """{"data":{"user":{"id":"18000000000000001","username":"example_user","is_private":false}}}"""

    @Test
    fun `a story tray looks the user up, then the reels`() {
        val http = trayHttp(profile, fixture("instagram_stories_tray.json"))
        val posts = fetcher(http).fetch("https://www.instagram.com/stories/example_user/", cookies(), token)
        assertTrue(http.requests[0].first.endsWith("users/web_profile_info/?username=example_user"))
        assertTrue(http.requests[1].first.endsWith("feed/reels_media/?reel_ids=18000000000000001"))
        assertTrue(posts.isNotEmpty())
        assertEquals("example_user", posts[0].owner)
    }

    @Test
    fun `a highlight asks for the highlight reel directly`() {
        val http = trayHttp(profile, fixture("instagram_stories_tray.json"))
        fetcher(http).fetch("https://www.instagram.com/stories/highlights/17900000000000001/", cookies(), token)
        assertEquals(1, http.requests.size)
        assertTrue(http.requests[0].first.contains("reel_ids=highlight%3A17900000000000001"))
    }

    @Test
    fun `an empty tray is no_media, which the story wording turns into expired`() {
        val http = trayHttp(profile, """{"reels_media": [], "status": "ok"}""")
        val e = failure { fetcher(http).fetch("https://www.instagram.com/stories/example_user/", cookies(), token) }
        assertEquals(MediaFailure.NO_MEDIA, e.failure)
    }

    @Test
    fun `an empty tray of a private account you do not follow is private`() {
        val priv = """{"data":{"user":{"id":"18000000000000001","is_private":true,"followed_by_viewer":false}}}"""
        val http = trayHttp(priv, """{"reels_media": []}""")
        val e = failure { fetcher(http).fetch("https://www.instagram.com/stories/example_user/", cookies(), token) }
        assertEquals(MediaFailure.PRIVATE, e.failure)
        val followed = """{"data":{"user":{"id":"18000000000000001","is_private":true,"followed_by_viewer":true}}}"""
        val again = failure { fetcher(trayHttp(followed, """{"reels_media": []}""")).fetch("https://www.instagram.com/stories/example_user/", cookies(), token) }
        assertEquals(MediaFailure.NO_MEDIA, again.failure)
    }

    @Test
    fun `an unknown user is not found and a missing sign-in is a login wall`() {
        val gone = trayHttp("""{"data":{"user":null}}""", "")
        assertEquals(MediaFailure.NOT_FOUND, failure { fetcher(gone).fetch("https://www.instagram.com/stories/nobody/", cookies(), token) }.failure)
        val http = FakeHttp().apply { onGet = { HttpResult(401, "") } }
        assertEquals(MediaFailure.LOGIN_REQUIRED, failure { fetcher(http).fetch("https://www.instagram.com/stories/example_user/", null, token) }.failure)
    }

    // -- TikTok ---------------------------------------------------------------
    private fun tiktokPage(item: String, status: Int = 0): String =
        """<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">""" +
            """{"__DEFAULT_SCOPE__":{"webapp.video-detail":{"statusCode":$status,"itemInfo":{"itemStruct":$item}}}}""" +
            "</script></html>"

    @Test
    fun `a tiktok photo page is read from its embedded json and gets no instagram cookies`() {
        val http = FakeHttp().apply { onGet = { HttpResult(200, tiktokPage(fixture("tiktok_photo_slideshow.json"))) } }
        val posts = fetcher(http).fetch("https://www.tiktok.com/@example_user/photo/7300000000000000001", cookies(), token)
        assertEquals("https://www.tiktok.com/@example_user/photo/7300000000000000001", http.requests.single().first)
        assertNull(http.requests.single().second["Cookie"])
        val post = posts.single()
        assertEquals(2, post.items.size)
        assertEquals("Sound Title", post.music?.title)
    }

    @Test
    fun `tiktok failures map to plain categories`() {
        fun run(page: HttpResult): MediaFailure = failure {
            fetcher(FakeHttp().apply { onGet = { page } }).fetch("https://www.tiktok.com/@u/photo/73", null, token)
        }.failure
        assertEquals(MediaFailure.PRIVATE, run(HttpResult(200, tiktokPage("{}", 10222))))
        assertEquals(MediaFailure.NOT_FOUND, run(HttpResult(200, tiktokPage("{}", 10204))))
        assertEquals(MediaFailure.UNKNOWN, run(HttpResult(200, "<html>no data</html>")))
        assertEquals(MediaFailure.NO_MEDIA, run(HttpResult(200, tiktokPage(fixture("tiktok_video_item.json")))))
        assertEquals(MediaFailure.NOT_FOUND, run(HttpResult(404, "")))
        assertEquals(MediaFailure.RATE_LIMITED, run(HttpResult(429, "")))
    }

    // -- cookies ----------------------------------------------------------------
    @Test
    fun `cookie header only carries cookies for the host`() {
        val file = cookies()
        assertEquals("sessionid=$secret; csrftoken=CSRF123", cookieHeader(file, "www.instagram.com"))
        assertNull(cookieHeader(file, "www.tiktok.com"))
        assertNull(cookieHeader(null, "www.instagram.com"))
        assertNull(cookieHeader(File(tmp.root, "missing.txt"), "www.instagram.com"))
        assertEquals("CSRF123", cookieValue(file, "www.instagram.com", "csrftoken"))
        assertNull(cookieValue(file, "www.instagram.com", "nope"))
    }

    // -- file downloads -------------------------------------------------------
    @Test
    fun `a download lands as a part file and is renamed when complete`() {
        val http = FakeHttp()
        val target = File(tmp.root, "dir/a.jpg")
        HttpFileDownloader(http).download("https://cdn.example.com/a.jpg", target, token)
        assertEquals("data", target.readText())
        assertFalse(File(tmp.root, "dir/a.jpg.part").exists())
    }

    @Test
    fun `download errors map to failures and leave no finished file`() {
        fun codeFor(code: Int): MediaFailure {
            val http = FakeHttp().apply { onDownload = { _, _ -> code } }
            val target = File(tmp.root, "x$code.jpg")
            val e = failure { HttpFileDownloader(http).download("https://cdn.example.com/a.jpg", target, token) }
            assertFalse(target.exists())
            return e.failure
        }
        assertEquals(MediaFailure.NOT_FOUND, codeFor(404))
        assertEquals(MediaFailure.NOT_FOUND, codeFor(410))
        assertEquals(MediaFailure.RATE_LIMITED, codeFor(429))
        assertEquals(MediaFailure.NETWORK, codeFor(502))
        assertEquals(MediaFailure.UNKNOWN, codeFor(403))
        assertEquals(MediaFailure.NETWORK, codeFor(416))
    }

    @Test
    fun `an io error while downloading is a network failure, and a cancelled token is quiet`() {
        val target = File(tmp.root, "n.jpg")
        val http = FakeHttp().apply { ioError = IOException("boom") }
        assertEquals(MediaFailure.NETWORK, failure { HttpFileDownloader(http).download("https://cdn.example.com/a.jpg", target, token) }.failure)
        val cancelled = CancelToken().also { it.cancel() }
        HttpFileDownloader(http).download("https://cdn.example.com/a.jpg", target, cancelled) // no exception
        assertFalse(target.exists())
    }

    @Test
    fun `an empty download is a failure`() {
        val http = FakeHttp().apply { onDownload = { _, part -> part.writeText(""); 200 } }
        val target = File(tmp.root, "e.jpg")
        assertEquals(MediaFailure.NETWORK, failure { HttpFileDownloader(http).download("https://cdn.example.com/a.jpg", target, token) }.failure)
        assertNotNull(target.parentFile)
        assertFalse(target.exists())
    }

    @Test
    fun `cancel runs the registered closers once`() {
        val t = CancelToken()
        var closed = 0
        t.onCancel { closed++ }
        t.cancel()
        t.cancel()
        assertEquals(1, closed)
        t.onCancel { closed++ } // late registration runs at once
        assertEquals(2, closed)
        assertTrue(t.cancelled)
    }
}
