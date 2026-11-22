package com.desolate.elisium.media

import com.desolate.elisium.engine.normalizeUrl
import com.desolate.elisium.engine.siteKind

/**
 * What kind of thing a link points at. The media engine only handles the image-bearing kinds;
 * reels and videos stay with yt-dlp, and everything else is [MediaUrlKind.UNKNOWN].
 */
enum class MediaUrlKind {
    /** `/p/<shortcode>` or `/tv/<shortcode>`: a post, photo or carousel. */
    POST,

    /** `/reel/<shortcode>`: a reel (yt-dlp's job unless it is a carousel). */
    REEL,

    /** `/stories/<user>/`: a whole story tray. */
    STORIES_USER,

    /** `/stories/<user>/<id>/`: one story. */
    STORY_ITEM,

    /** `/stories/highlights/<id>/`: one highlight tray. */
    HIGHLIGHT,

    /** TikTok `@user/photo/<id>`: a photo slideshow. */
    TIKTOK_PHOTO,

    /** Anything else, including share links that need a network redirect to resolve. */
    UNKNOWN,
}

/** A classified link. Only the fields that belong to [kind] are set. */
data class MediaUrl(
    val kind: MediaUrlKind,
    val site: String? = null,
    val shortcode: String? = null,
    val username: String? = null,
    val storyId: String? = null,
    val highlightId: String? = null,
    val tiktokId: String? = null,
)

private val UNKNOWN_URL = MediaUrl(MediaUrlKind.UNKNOWN)
private val SHORTCODE_RE = Regex("[A-Za-z0-9_-]+")
private val POST_PATHS = setOf("p", "tv")

/**
 * Classifies [url] without any network call. Normalisation is delegated to the engine's
 * read-only [normalizeUrl], so tracking parameters and `www.`/`m.` hosts behave exactly as
 * they do for the queue's dedupe.
 */
fun classifyMediaUrl(url: String?): MediaUrl {
    if (url.isNullOrBlank()) return UNKNOWN_URL
    val normalised = try {
        normalizeUrl(url)
    } catch (_: IllegalArgumentException) {
        return UNKNOWN_URL
    }
    val site = siteKind(normalised) ?: return UNKNOWN_URL
    val segments = pathSegments(normalised) ?: return UNKNOWN_URL
    return when (site) {
        MediaSites.INSTAGRAM -> classifyInstagram(segments)
        MediaSites.TIKTOK -> classifyTikTok(segments)
        else -> UNKNOWN_URL
    }
}

private fun classifyInstagram(segments: List<String>): MediaUrl {
    if (segments.isEmpty()) return UNKNOWN_URL
    val first = segments[0]
    if (segments.size >= 2 && (first in POST_PATHS || first == "reel")) {
        val shortcode = segments[1]
        if (!SHORTCODE_RE.matches(shortcode)) return UNKNOWN_URL
        return MediaUrl(
            kind = if (first == "reel") MediaUrlKind.REEL else MediaUrlKind.POST,
            site = MediaSites.INSTAGRAM,
            shortcode = shortcode,
        )
    }
    if (first != "stories") return UNKNOWN_URL
    if (segments.size == 3 && segments[1] == "highlights") {
        val highlightId = segments[2]
        if (!isAllDigits(highlightId)) return UNKNOWN_URL
        return MediaUrl(
            kind = MediaUrlKind.HIGHLIGHT,
            site = MediaSites.INSTAGRAM,
            highlightId = highlightId,
        )
    }
    if (segments.size == 2 && segments[1] != "highlights") {
        return MediaUrl(
            kind = MediaUrlKind.STORIES_USER,
            site = MediaSites.INSTAGRAM,
            username = segments[1],
        )
    }
    if (segments.size >= 3 && segments[1] != "highlights") {
        val storyId = segments[2]
        if (!isAllDigits(storyId)) return UNKNOWN_URL
        return MediaUrl(
            kind = MediaUrlKind.STORY_ITEM,
            site = MediaSites.INSTAGRAM,
            username = segments[1],
            storyId = storyId,
        )
    }
    return UNKNOWN_URL
}

private fun classifyTikTok(segments: List<String>): MediaUrl {
    if (segments.size < 3) return UNKNOWN_URL
    val user = segments[0]
    if (!user.startsWith("@") || user.length == 1) return UNKNOWN_URL
    if (segments[1] != "photo") return UNKNOWN_URL
    val tiktokId = segments[2]
    if (!isAllDigits(tiktokId)) return UNKNOWN_URL
    return MediaUrl(
        kind = MediaUrlKind.TIKTOK_PHOTO,
        site = MediaSites.TIKTOK,
        username = user.substring(1),
        tiktokId = tiktokId,
    )
}

private fun isAllDigits(text: String): Boolean = text.isNotEmpty() && text.all { it in '0'..'9' }

/** The path segments of an already-normalised absolute URL, or null. */
private fun pathSegments(url: String): List<String>? {
    val schemeEnd = url.indexOf("://")
    if (schemeEnd < 0) return null
    val rest = url.substring(schemeEnd + 3)
    val slash = rest.indexOf('/')
    if (slash < 0) return emptyList()
    val path = rest.substring(slash).substringBefore('?').substringBefore('#')
    return path.split('/').filter { it.isNotEmpty() }
}
