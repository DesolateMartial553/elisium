package com.desolate.elisium.media

/*
 * Pure-JVM models for the Android media engine (brief 10A). No Android APIs: the same
 * classes carry into 10D, where a small network client feeds the parsers below.
 */

/** What one downloadable file of a post is. */
enum class MediaKind { IMAGE, VIDEO, AUDIO }

/**
 * One downloadable file of a post.
 *
 * [index] is the 1-based slide number (a song saved as its own file comes after the slides).
 * [mediaId] is the identity used in the archive key: an Instagram slide's numeric media id,
 * or `<tiktok id>_<n>` for a TikTok photo.
 */
data class MediaItem(
    val kind: MediaKind,
    val url: String,
    val width: Int? = null,
    val height: Int? = null,
    val index: Int,
    val mediaId: String,
    val ext: String,
)

/**
 * The song a post uses. Instagram and TikTok keep it as a separate file, never inside the
 * image; [startMs]/[durationMs] describe the snippet the post plays, when the site says.
 */
data class MusicClip(
    val url: String,
    val title: String? = null,
    val artist: String? = null,
    val startMs: Long? = null,
    val durationMs: Long? = null,
)

/** One post or story item, already resolved to downloadable files. */
data class MediaPost(
    val site: String,
    val id: String,
    val owner: String? = null,
    val takenAt: Long? = null,
    val caption: String? = null,
    val items: List<MediaItem>,
    val music: MusicClip? = null,
)

/**
 * Why a response could not become a [MediaPost]:
 * - [NoMedia]: the JSON is fine but holds no image/video (an empty response, or a video-only
 *   TikTok item), so the URL stays with yt-dlp;
 * - [LoginRequired]: the site answered with a sign-in wall (stories, private posts);
 * - [Unknown]: not JSON, or a shape this parser does not recognise.
 */
sealed interface MediaError {
    data object NoMedia : MediaError
    data object LoginRequired : MediaError
    data object Unknown : MediaError
}

/** The result of parsing one response. A story tray returns one post per story item. */
sealed interface MediaResult {
    data class Ok(val posts: List<MediaPost>) : MediaResult {
        constructor(post: MediaPost) : this(listOf(post))
    }

    data class Failed(val error: MediaError) : MediaResult
}

/** Site names used in [MediaPost.site] and in archive keys. */
object MediaSites {
    const val INSTAGRAM = "instagram"
    const val TIKTOK = "tiktok"
}
