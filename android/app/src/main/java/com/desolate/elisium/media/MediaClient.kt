package com.desolate.elisium.media

import java.io.File
import java.io.IOException

private const val IG_HOST = "www.instagram.com"
private const val IG_API = "https://$IG_HOST/api/v1"
private const val IG_APP_ID = "936619743392459"
private const val TIKTOK_HOST = "www.tiktok.com"
private val TIKTOK_DATA = Regex(
    "<script[^>]*id=\"__UNIVERSAL_DATA_FOR_REHYDRATION__\"[^>]*>(.*?)</script>",
    RegexOption.DOT_MATCHES_ALL,
)

/**
 * Our own small Instagram / TikTok client (brief 10D, route (c) of 10A): fetch the post JSON with the stored
 * session cookies, feed the 10A parsers, return [MediaPost]s. No gallery-dl code or dependency.
 *
 * The cookie header is built per request and never kept, logged, or put in an exception message.
 * Every HTTP status and response is mapped to a [MediaFailure] (see `MediaErrors.kt` for the words).
 */
class HttpMediaFetcher(private val http: HttpTransport) : MediaFetcher {

    override fun fetch(url: String, cookiesFile: File?, token: CancelToken): List<MediaPost> {
        val target = classifyMediaUrl(url)
        return when (target.kind) {
            MediaUrlKind.POST -> instagramPost(target, cookiesFile, token)
            MediaUrlKind.STORIES_USER -> instagramTray(target, cookiesFile, token)
            MediaUrlKind.STORY_ITEM -> instagramTray(target, cookiesFile, token)
            MediaUrlKind.HIGHLIGHT -> instagramReels("highlight:${target.highlightId}", cookiesFile, token)
            MediaUrlKind.TIKTOK_PHOTO -> tiktokPhoto(target, token)
            else -> throw MediaFetchException(MediaFailure.NO_MEDIA, "not a photo or story link")
        }
    }

    // -- Instagram ---------------------------------------------------------
    private fun igHeaders(cookiesFile: File?): Map<String, String> {
        val headers = linkedMapOf(
            "User-Agent" to BROWSER_USER_AGENT,
            "Accept" to "*/*",
            "X-IG-App-ID" to IG_APP_ID,
            "X-Requested-With" to "XMLHttpRequest",
            "Referer" to "https://$IG_HOST/",
        )
        cookieHeader(cookiesFile, IG_HOST)?.let { headers["Cookie"] = it }
        cookieValue(cookiesFile, IG_HOST, "csrftoken")?.let { headers["X-CSRFToken"] = it }
        return headers
    }

    private fun igGet(path: String, cookiesFile: File?, token: CancelToken): String {
        val result = request("$IG_API/$path", igHeaders(cookiesFile), token)
        when (result.code) {
            in 200..299 -> Unit
            429 -> throw MediaFetchException(MediaFailure.RATE_LIMITED, "HTTP 429")
            401, 403 -> throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP ${result.code}")
            404 -> throw MediaFetchException(MediaFailure.NOT_FOUND, "HTTP 404")
            400 -> if (looksLikeLoginWall(result.body)) {
                throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP 400")
            } else if (looksRateLimited(result.body)) {
                throw MediaFetchException(MediaFailure.RATE_LIMITED, "HTTP 400")
            } else {
                throw MediaFetchException(MediaFailure.UNKNOWN, "HTTP 400")
            }
            else -> throw MediaFetchException(
                if (result.code >= 500) MediaFailure.NETWORK else MediaFailure.UNKNOWN,
                "HTTP ${result.code}",
            )
        }
        // A 200 is a real answer; only Instagram's own failure payload counts as pacing, never a caption.
        if (looksRateLimited(result.body) && result.body.replace(" ", "").contains("\"status\":\"fail\"")) {
            throw MediaFetchException(MediaFailure.RATE_LIMITED, "rate limited")
        }
        return result.body
    }

    private fun looksLikeLoginWall(body: String): Boolean {
        val text = body.lowercase()
        return "login_required" in text || "checkpoint_required" in text || "require_login" in text
    }

    private fun looksRateLimited(body: String): Boolean = "please wait a few minutes" in body.lowercase()

    private fun instagramPost(target: MediaUrl, cookiesFile: File?, token: CancelToken): List<MediaPost> {
        val shortcode = target.shortcode ?: throw MediaFetchException(MediaFailure.NO_MEDIA, "no shortcode")
        val mediaId = ShortcodeId.toMediaId(shortcode)
            ?: throw MediaFetchException(MediaFailure.NOT_FOUND, "bad shortcode")
        val body = igGet("media/$mediaId/info/", cookiesFile, token)
        return resolve(InstagramParser.parseMediaInfo(body))
    }

    private fun instagramTray(target: MediaUrl, cookiesFile: File?, token: CancelToken): List<MediaPost> {
        val username = target.username ?: throw MediaFetchException(MediaFailure.NO_MEDIA, "no user")
        val profile = igGet("users/web_profile_info/?username=${java.net.URLEncoder.encode(username, "UTF-8")}", cookiesFile, token)
        val user = parseJsonObject(profile).obj("data").obj("user")
            ?: throw MediaFetchException(MediaFailure.NOT_FOUND, "no such user")
        val userId = user.text("id") ?: throw MediaFetchException(MediaFailure.NOT_FOUND, "no user id")
        return try {
            instagramReels(userId, cookiesFile, token)
        } catch (e: MediaFetchException) {
            // An empty tray of a private account you do not follow is "private", not "expired".
            if (e.failure == MediaFailure.NO_MEDIA &&
                user.flag("is_private") == true && user.flag("followed_by_viewer") != true
            ) {
                throw MediaFetchException(MediaFailure.PRIVATE, "private account")
            }
            throw e
        }
    }

    private fun instagramReels(reelId: String, cookiesFile: File?, token: CancelToken): List<MediaPost> {
        val body = igGet("feed/reels_media/?reel_ids=${java.net.URLEncoder.encode(reelId, "UTF-8")}", cookiesFile, token)
        return resolve(InstagramParser.parseStoriesTray(body))
    }

    // -- TikTok ------------------------------------------------------------
    private fun tiktokPhoto(target: MediaUrl, token: CancelToken): List<MediaPost> {
        val id = target.tiktokId ?: throw MediaFetchException(MediaFailure.NO_MEDIA, "no id")
        val headers = mapOf("User-Agent" to BROWSER_USER_AGENT, "Accept" to "text/html,*/*", "Referer" to "https://$TIKTOK_HOST/")
        val result = request("https://$TIKTOK_HOST/@${target.username}/photo/$id", headers, token)
        when (result.code) {
            in 200..299 -> Unit
            429 -> throw MediaFetchException(MediaFailure.RATE_LIMITED, "HTTP 429")
            401, 403 -> throw MediaFetchException(MediaFailure.LOGIN_REQUIRED, "HTTP ${result.code}")
            404 -> throw MediaFetchException(MediaFailure.NOT_FOUND, "HTTP 404")
            else -> throw MediaFetchException(
                if (result.code >= 500) MediaFailure.NETWORK else MediaFailure.UNKNOWN,
                "HTTP ${result.code}",
            )
        }
        val data = TIKTOK_DATA.find(result.body)?.groupValues?.get(1)
            ?: throw MediaFetchException(MediaFailure.UNKNOWN, "no page data")
        val detail = parseJsonObject(data).obj("__DEFAULT_SCOPE__").obj("webapp.video-detail")
        when (detail.number("statusCode")) {
            null, 0L -> Unit
            10222L -> throw MediaFetchException(MediaFailure.PRIVATE, "private")
            else -> throw MediaFetchException(MediaFailure.NOT_FOUND, "status ${detail.number("statusCode")}")
        }
        val item = detail.obj("itemInfo").obj("itemStruct")
            ?: throw MediaFetchException(MediaFailure.NOT_FOUND, "no item")
        return resolve(TikTokParser.parseItem(item.toString()))
    }

    // -- shared --------------------------------------------------------------
    private fun request(url: String, headers: Map<String, String>, token: CancelToken): HttpResult {
        try {
            return http.get(url, headers, token)
        } catch (e: IOException) {
            if (token.cancelled) throw MediaFetchException(MediaFailure.NETWORK, "cancelled")
            throw MediaFetchException(MediaFailure.NETWORK, e.javaClass.simpleName)
        }
    }

    private fun resolve(result: MediaResult): List<MediaPost> = when (result) {
        is MediaResult.Ok -> result.posts
        is MediaResult.Failed -> throw MediaFetchException(
            when (result.error) {
                MediaError.NoMedia -> MediaFailure.NO_MEDIA
                MediaError.LoginRequired -> MediaFailure.LOGIN_REQUIRED
                MediaError.Unknown -> MediaFailure.UNKNOWN
            },
            result.error.toString(),
        )
    }

}

/** Saves a file over [http]; an HTTP error or IO failure becomes a [MediaFetchException]. */
class HttpFileDownloader(private val http: HttpTransport) : FileDownloader {
    override fun download(url: String, target: File, token: CancelToken) {
        val part = File(target.parentFile, target.name + ".part")
        target.parentFile?.mkdirs()
        val code = try {
            http.download(url, mapOf("User-Agent" to BROWSER_USER_AGENT, "Accept" to "*/*"), part, token)
        } catch (e: IOException) {
            if (token.cancelled) return
            throw MediaFetchException(MediaFailure.NETWORK, e.javaClass.simpleName)
        }
        if (token.cancelled) return
        when (code) {
            in 200..299 -> Unit
            404, 410 -> {
                part.delete()
                throw MediaFetchException(MediaFailure.NOT_FOUND, "HTTP $code")
            }
            416 -> {
                part.delete()
                throw MediaFetchException(MediaFailure.NETWORK, "HTTP 416")
            }
            429 -> throw MediaFetchException(MediaFailure.RATE_LIMITED, "HTTP 429")
            else -> throw MediaFetchException(
                if (code >= 500) MediaFailure.NETWORK else MediaFailure.UNKNOWN,
                "HTTP $code",
            )
        }
        if (!part.isFile || part.length() == 0L) {
            part.delete()
            throw MediaFetchException(MediaFailure.NETWORK, "empty file")
        }
        if (!part.renameTo(target)) {
            part.copyTo(target, overwrite = true)
            part.delete()
        }
    }
}
