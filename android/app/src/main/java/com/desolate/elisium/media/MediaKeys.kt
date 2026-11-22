package com.desolate.elisium.media

/**
 * Archive keys for media-engine files, as `(extractor, id)` pairs for the engine's [Archive].
 *
 * - one key per slide: `instagram <mediaId>` / `tiktok <id>_<n>`
 * - the built slideshow mp4: `instagram <shortcode>_mix` / `tiktok <id>_mix`
 *
 * A post re-added later therefore fetches only the files it is missing.
 */
object MediaKeys {
    /** The key for one downloaded file. */
    fun slide(post: MediaPost, item: MediaItem): Pair<String, String> =
        post.site.lowercase() to item.mediaId

    /** The key for the mp4 built from the post's photos, videos and song. */
    fun mix(post: MediaPost): Pair<String, String> = post.site.lowercase() to "${post.id}_mix"

    /** `"instagram 123"`, the archive line for [key]. */
    fun entry(key: Pair<String, String>): String = "${key.first} ${key.second}"
}
