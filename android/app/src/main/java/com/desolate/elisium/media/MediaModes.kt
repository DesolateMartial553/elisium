package com.desolate.elisium.media

/** "Photo posts with a song" (Settings): what a post with pictures and a song becomes. */
enum class PhotoMode(val storedValue: String) {
    /** Photos, the song and a video built from them (default). */
    PhotosSongVideo("video"),

    /** Photos and the song file only. */
    PhotosSong("song"),

    /** Photos only; the song is not downloaded. */
    PhotosOnly("photos"),
    ;

    companion object {
        fun fromStored(value: String?): PhotoMode = entries.firstOrNull { it.storedValue == value } ?: PhotosSongVideo
    }
}

/** "Song length" (Settings): the snippet the post plays (default) or the whole track. */
enum class SongLength(val storedValue: String) {
    Snippet("snippet"),
    Full("full"),
    ;

    companion object {
        fun fromStored(value: String?): SongLength = entries.firstOrNull { it.storedValue == value } ?: Snippet
    }
}

/** Which engine a link needs (same table as the desktop `media.route_for`). */
enum class MediaRoute {
    /** Reels, videos, everything else: yt-dlp, unchanged. */
    YTDLP,

    /** Story trays, highlights, TikTok photo posts: the media engine only. */
    MEDIA,

    /** Instagram posts and single stories: yt-dlp first, the media engine when it says `no_media`. */
    YTDLP_THEN_MEDIA,
}

fun routeFor(url: String?): MediaRoute = when (classifyMediaUrl(url).kind) {
    MediaUrlKind.STORIES_USER, MediaUrlKind.HIGHLIGHT, MediaUrlKind.TIKTOK_PHOTO -> MediaRoute.MEDIA
    MediaUrlKind.POST, MediaUrlKind.STORY_ITEM -> MediaRoute.YTDLP_THEN_MEDIA
    else -> MediaRoute.YTDLP
}
