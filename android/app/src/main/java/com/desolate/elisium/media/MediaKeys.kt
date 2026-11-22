package com.desolate.elisium.media

/**
 * Archive keys for media-engine files, as `(extractor, id)` pairs for the engine's [Archive].
 *
 * - one key per slide: `instagram <mediaId>` / `tiktok <id>_<n>`
 * - the built slideshow mp4: `instagram <shortcode>_mix` / `tiktok <id>_mix`
 * - the song file: `instagram <shortcode>_song` / `tiktok <id>_song`
 *
 * A post re-added later therefore fetches only the files it is missing.
 */
object MediaKeys {
    /** The key for one downloaded file. */
    fun slide(post: MediaPost, item: MediaItem): Pair<String, String> =
        post.site.lowercase() to item.mediaId

    /** The key for the mp4 built from the post's photos, videos and song. */
    fun mix(post: MediaPost): Pair<String, String> = post.site.lowercase() to "${post.id}_mix"

    /** The key for the post's song file (`instagram <shortcode>_song`). */
    fun song(post: MediaPost): Pair<String, String> = post.site.lowercase() to "${post.id}_song"

    /** `"instagram 123"`, the archive line for [key]. */
    fun entry(key: Pair<String, String>): String = "${key.first} ${key.second}"
}
