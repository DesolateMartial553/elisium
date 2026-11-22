package com.desolate.elisium.media

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

/**
 * Reads Instagram's public media-info JSON (`api/v1/media/{id}/info/`) and story-tray JSON
 * (`feed/reels_media/`). Only public field names are used; no gallery-dl code is copied.
 *
 * The parser is deliberately tolerant: a missing field never throws, it narrows the result
 * to a [MediaError] instead. A post whose slides are all unusable is [MediaError.NoMedia];
 * a response that is not the expected JSON shape is [MediaError.Unknown].
 */
object InstagramParser {
    private const val MEDIA_TYPE_IMAGE = 1L
    private const val MEDIA_TYPE_VIDEO = 2L
    private const val MEDIA_TYPE_CAROUSEL = 8L

    /** One post or carousel: `items[0]` with `carousel_media[]` when `media_type` is 8. */
    fun parseMediaInfo(json: String?): MediaResult {
        val root = parseJsonObject(json) ?: return MediaResult.Failed(MediaError.Unknown)
        if (loginRequired(root)) return MediaResult.Failed(MediaError.LoginRequired)
        val item = root.arr("items")?.firstObject() ?: return MediaResult.Failed(MediaError.NoMedia)
        return parsePostItem(item)
    }

    /**
     * A whole story tray: `reels_media[]` (or the `reels{}` map keyed by reel id), each reel's
     * `items[]` becoming one [MediaPost]. Unusable stories are skipped, never fatal.
     */
    fun parseStoriesTray(json: String?): MediaResult {
        val root = parseJsonObject(json) ?: return MediaResult.Failed(MediaError.Unknown)
        if (loginRequired(root)) return MediaResult.Failed(MediaError.LoginRequired)
        val reels: List<JsonObject> = root.arr("reels_media")?.objects()
            ?: root.obj("reels")?.values?.filterIsInstance<JsonObject>()
            ?: emptyList()
        val posts = ArrayList<MediaPost>()
        for (reel in reels) {
            val owner = reel.obj("user")?.text("username")
            for (story in reel.arr("items")?.objects().orEmpty()) {
                storyPost(story, owner)?.let { posts.add(it) }
            }
        }
        if (posts.isEmpty()) return MediaResult.Failed(MediaError.NoMedia)
        return MediaResult.Ok(posts)
    }

    private fun parsePostItem(item: JsonObject): MediaResult {
        val mediaType = item.number("media_type")
        val shortcode = item.text("code")
        val postId = shortcode ?: item.text("id") ?: return MediaResult.Failed(MediaError.Unknown)
        val slides: List<JsonObject> = if (mediaType == MEDIA_TYPE_CAROUSEL || item.arr("carousel_media") != null) {
            item.arr("carousel_media")?.objects().orEmpty()
        } else {
            listOf(item)
        }
        val items = ArrayList<MediaItem>()
        for (slide in slides) {
            // The index counts only the slides that resolved, so it always matches the file list.
            slideItem(slide, items.size + 1)?.let { items.add(it) }
        }
        if (items.isEmpty()) return MediaResult.Failed(MediaError.NoMedia)
        return MediaResult.Ok(
            MediaPost(
                site = MediaSites.INSTAGRAM,
                id = postId,
                owner = item.obj("user")?.text("username"),
                takenAt = item.number("taken_at"),
                caption = captionOf(item),
                items = items,
                music = musicOf(item),
            ),
        )
    }

    /** One story item. A story without an id or a usable URL is skipped by the caller. */
    private fun storyPost(story: JsonObject, owner: String?): MediaPost? {
        val mediaId = story.text("pk") ?: story.text("id") ?: return null
        val item = slideItem(story, 1) ?: return null
        return MediaPost(
            site = MediaSites.INSTAGRAM,
            id = mediaId,
            owner = owner ?: story.obj("user")?.text("username"),
            takenAt = story.number("taken_at"),
            caption = captionOf(story),
            items = listOf(item),
            music = stickerMusic(story) ?: musicOf(story),
        )
    }

    /**
     * The best candidate of one slide, or null when it has no identity or no URL.
     * `media_type` 1 is an image, 2 a video; anything else is guessed from what is present.
     */
    private fun slideItem(slide: JsonObject, index: Int): MediaItem? {
        val mediaId = slide.text("pk") ?: slide.text("id") ?: return null
        val kind = when (slide.number("media_type")) {
            MEDIA_TYPE_VIDEO -> MediaKind.VIDEO
            MEDIA_TYPE_IMAGE -> MediaKind.IMAGE
            else -> if (slide.arr("video_versions") != null) MediaKind.VIDEO else MediaKind.IMAGE
        }
        val candidate = when (kind) {
            MediaKind.VIDEO -> largest(slide.arr("video_versions"))
            else -> largest(slide.obj("image_versions2")?.arr("candidates"))
        } ?: return null
        val fallback = if (kind == MediaKind.VIDEO) "mp4" else "jpg"
        return MediaItem(
            kind = kind,
            url = candidate.url,
            width = candidate.width,
            height = candidate.height,
            index = index,
            mediaId = mediaId,
            ext = guessExt(candidate.url, fallback),
        )
    }

    private data class Candidate(val url: String, val width: Int?, val height: Int?)

    /** The largest candidate by pixel area; the first one wins a tie, a missing size counts as 0. */
    private fun largest(candidates: JsonArray?): Candidate? {
        if (candidates == null) return null
        var best: Candidate? = null
        var bestArea = -1L
        for (element in candidates) {
            val obj = element as? JsonObject ?: continue
            val url = obj.text("url") ?: continue
            val width = obj.number("width")?.toInt()
            val height = obj.number("height")?.toInt()
            val area = (width ?: 0).toLong() * (height ?: 0)
            if (best == null || area > bestArea) {
                best = Candidate(url, width, height)
                bestArea = area
            }
        }
        return best
    }

    private fun captionOf(item: JsonObject): String? =
        item.obj("caption")?.text("text") ?: item.text("caption_text")

    /** `music_metadata.music_info.music_asset_info` plus the snippet from `music_consumption_info`. */
    private fun musicOf(item: JsonObject): MusicClip? {
        val metadata = item.obj("music_metadata")
        val info = metadata?.obj("music_info")
        val asset = info?.obj("music_asset_info") ?: metadata?.obj("music_asset_info")
        val consumption = info?.obj("music_consumption_info")
            ?: metadata?.obj("music_consumption_info")
            ?: item.obj("music_consumption_info")
        return clip(asset, consumption)
    }

    /** A story's `story_music_stickers[].music_asset_info`, first sticker with a URL wins. */
    private fun stickerMusic(story: JsonObject): MusicClip? {
        for (sticker in story.arr("story_music_stickers")?.objects().orEmpty()) {
            val asset = sticker.obj("music_asset_info") ?: continue
            val consumption = sticker.obj("music_consumption_info") ?: asset.obj("music_consumption_info")
            clip(asset, consumption)?.let { return it }
        }
        return null
    }

    private fun clip(asset: JsonObject?, consumption: JsonObject?): MusicClip? {
        val url = asset?.text("progressive_download_url") ?: return null
        return MusicClip(
            url = url,
            title = asset.text("title"),
            artist = asset.text("display_artist") ?: asset.text("artist_name"),
            startMs = consumption?.firstNumber("highlight_start_times_in_ms")
                ?: asset.firstNumber("highlight_start_times_in_ms"),
            durationMs = consumption?.number("duration_in_ms") ?: asset.number("duration_in_ms"),
        )
    }

    /** Instagram's sign-in wall, as returned for stories and private posts. */
    private fun loginRequired(root: JsonObject): Boolean {
        if (root.flag("require_login") == true) return true
        val message = root.text("message")?.lowercase() ?: return false
        return "login_required" in message ||
            "checkpoint_required" in message ||
            "login required" in message
    }
}
