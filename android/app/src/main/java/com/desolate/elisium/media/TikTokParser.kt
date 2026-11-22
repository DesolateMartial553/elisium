package com.desolate.elisium.media

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Reads one TikTok item JSON. Only photo slideshows (`imagePost.images[]`) are handled here;
 * a video item is [MediaError.NoMedia] so the URL stays with yt-dlp.
 */
object TikTokParser {
    /** `imagePost.images[].imageURL.urlList[]` plus `music.playUrl`. */
    fun parseItem(json: String?): MediaResult {
        val root = parseJsonObject(json) ?: return MediaResult.Failed(MediaError.Unknown)
        if (root.flag("requireLogin") == true || root.flag("require_login") == true) {
            return MediaResult.Failed(MediaError.LoginRequired)
        }
        val id = root.text("id") ?: return MediaResult.Failed(MediaError.Unknown)
        val images = root.obj("imagePost")?.arr("images")?.objects().orEmpty()
        val items = ArrayList<MediaItem>()
        for (image in images) {
            val url = firstUrl(image.obj("imageURL")?.arr("urlList")) ?: continue
            items.add(
                MediaItem(
                    kind = MediaKind.IMAGE,
                    url = url,
                    width = image.number("imageWidth")?.toInt(),
                    height = image.number("imageHeight")?.toInt(),
                    index = items.size + 1,
                    // The per-photo archive key is `tiktok <id>_<n>` (brief 10A).
                    mediaId = "${id}_${items.size + 1}",
                    ext = guessExt(url, "jpg"),
                ),
            )
        }
        if (items.isEmpty()) return MediaResult.Failed(MediaError.NoMedia)
        val music = root.obj("music")
        return MediaResult.Ok(
            MediaPost(
                site = MediaSites.TIKTOK,
                id = id,
                owner = root.obj("author")?.text("uniqueId"),
                takenAt = root.number("createTime"),
                caption = root.text("desc"),
                items = items,
                music = music?.text("playUrl")?.let { url ->
                    MusicClip(
                        url = url,
                        title = music.text("title"),
                        artist = music.text("authorName"),
                    )
                },
            ),
        )
    }

    /** The first usable URL of an `urlList` (TikTok lists the largest image first). */
    private fun firstUrl(list: JsonArray?): String? =
        list?.firstNotNullOfOrNull { (it as? JsonPrimitive)?.contentOrNull }?.takeIf { it.isNotBlank() }
}
