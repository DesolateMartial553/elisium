package com.desolate.elisium.engine

import com.desolate.elisium.media.CancelToken
import com.desolate.elisium.media.MediaEngine
import com.desolate.elisium.media.MediaFailure
import com.desolate.elisium.media.MediaFetchException
import com.desolate.elisium.media.MediaItem
import com.desolate.elisium.media.MediaKeys
import com.desolate.elisium.media.MediaKind
import com.desolate.elisium.media.MediaPost
import com.desolate.elisium.media.MediaUrlKind
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import com.desolate.elisium.media.Visual
import com.desolate.elisium.media.classifyMediaUrl
import com.desolate.elisium.media.convertStaging
import com.desolate.elisium.media.fullSongName
import com.desolate.elisium.media.guessExt
import com.desolate.elisium.media.markerOf
import com.desolate.elisium.media.mediaErrorInfo
import com.desolate.elisium.media.mediaFileName
import com.desolate.elisium.media.postBase
import com.desolate.elisium.media.safeFolderName
import com.desolate.elisium.media.songName
import java.io.File
import kotlinx.coroutines.CancellationException

/** The note an item carries when everything it names was already in the output folder. */
const val ALREADY_SAVED_NOTE = "Already saved"

/** What the queue hands the runner for one attempt. */
class MediaRunRequest(
    val url: String,
    val cookiesFile: File?,
    /** "Download again anyway": ignore the media archive for this run. */
    val force: Boolean,
    val photoMode: PhotoMode,
    val songLength: SongLength,
    /** The item's own staging folder (finished files and `.part` files stay in it between pause and resume). */
    val dir: File,
)

sealed interface MediaOutcome {
    data class Done(val firstLocation: String?, val note: String?, val filesTotal: Int) : MediaOutcome
    data class Skipped(val note: String?, val filesTotal: Int) : MediaOutcome
    data class Failed(val error: ErrorInfo) : MediaOutcome

    /** Paused or cancelled by the user. */
    data object Stopped : MediaOutcome
}

/** The queue's side of one media attempt. */
interface MediaHooks {
    /** The files are known: card title, thumbnail, "6 photos + song", total. False means stop now. */
    fun planned(title: String?, thumbnail: String?, formatLabel: String?, filesTotal: Int): Boolean
    fun progress(done: Int, total: Int)

    /** The first ffmpeg run is about to start (the item becomes `converting`). */
    fun converting()
    fun stopped(): Boolean
}

private class Planned(
    val post: MediaPost,
    val kind: MediaKind,
    val url: String,
    val stagedName: String,
    val marker: String,
    val key: Pair<String, String>,
    val item: MediaItem?,
) {
    val isSong: Boolean get() = item == null
}

/**
 * One media-engine attempt: look the post up, plan its files, skip what the media archive and the output
 * folder already have, download the rest into [MediaRunRequest.dir], cut the song / build the video, move
 * everything to the output store (owner subfolder) and archive each file. The behaviour mirrors the desktop
 * `_media_attempt`; errors are returned, never thrown (except cancellation).
 */
class MediaRunner(
    private val engine: MediaEngine,
    private val archive: Archive,
    private val store: OutputStore,
) {
    suspend fun run(req: MediaRunRequest, hooks: MediaHooks, token: CancelToken): MediaOutcome {
        val hasCookies = req.cookiesFile != null
        val target = classifyMediaUrl(req.url)
        var posts = try {
            engine.fetcher.fetch(req.url, req.cookiesFile, token)
        } catch (e: MediaFetchException) {
            if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
            return MediaOutcome.Failed(mediaErrorInfo(e.failure, req.url, hasCookies))
        }
        if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
        if (target.kind == MediaUrlKind.STORY_ITEM) posts = posts.filter { it.id == target.storyId }
        if (posts.isEmpty()) return MediaOutcome.Failed(mediaErrorInfo(MediaFailure.NO_MEDIA, req.url, hasCookies))

        val owner = safeFolderName(posts.firstNotNullOfOrNull { it.owner } ?: target.username)
        val single = posts.size == 1 && target.kind in setOf(
            MediaUrlKind.POST, MediaUrlKind.STORY_ITEM, MediaUrlKind.TIKTOK_PHOTO,
        )
        val bases = posts.associateWith { postBase(it, target.username) }
        val wantSong = req.photoMode != PhotoMode.PhotosOnly

        // -- plan ------------------------------------------------------------
        val planned = ArrayList<Planned>()
        for (post in posts) {
            val base = bases.getValue(post)
            for (item in post.items) {
                planned.add(
                    Planned(post, item.kind, item.url, mediaFileName(base, item), item.mediaId, MediaKeys.slide(post, item), item),
                )
            }
            val music = post.music
            if (wantSong && music != null) {
                val ext = guessExt(music.url, "m4a")
                planned.add(
                    Planned(post, MediaKind.AUDIO, music.url, fullSongName(base, post, ext), "${post.id}_song", MediaKeys.song(post), null),
                )
            }
        }
        val session = engine.ffmpeg()
        session?.let { s -> token.onCancel { s.terminate() } }
        val post0 = posts.first()
        val mixMarker = "${post0.id}_mix"
        val mixPresent = single && store.existsInFolder(owner, mixMarker)
        val visualsCount = post0.items.size
        val hasSong = planned.any { it.isSong }
        val mixWanted = single && req.photoMode == PhotoMode.PhotosSongVideo && hasSong && visualsCount >= 1 && !mixPresent
        val mixExpected = mixWanted && session != null
        var total = planned.size + if (mixExpected) 1 else 0

        val photos = planned.count { it.kind == MediaKind.IMAGE }
        val videos = planned.count { it.kind == MediaKind.VIDEO }
        val label = buildList {
            if (photos > 0) add("$photos photo${if (photos != 1) "s" else ""}")
            if (videos > 0) add("$videos video${if (videos != 1) "s" else ""}")
            val songs = planned.count { it.isSong }
            if (songs == 1) add("song") else if (songs > 1) add("$songs songs")
        }.joinToString(" + ").ifEmpty { null }
        val title = titleOf(post0, owner)
        val thumbnail = planned.firstOrNull { it.kind == MediaKind.IMAGE }?.url
        if (!hooks.planned(title, thumbnail, label, total)) return MediaOutcome.Stopped

        // -- download what is missing --------------------------------------
        req.dir.mkdirs()
        var done = 0
        for (file in planned) {
            if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
            val staged = File(req.dir, file.stagedName)
            // A video that will really be built needs its photos and song even when those are already saved.
            // Without ffmpeg nothing is built, so saved files are never fetched again just for it.
            val have = !req.force && !mixExpected && archivedAndPresent(file, owner)
            val cutStaged = file.isSong && req.dir.listFiles()
                ?.any { it.isFile && it.name.startsWith("${bases.getValue(file.post)} song [${file.post.id}_song].") } == true
            if (have || staged.isFile || cutStaged) {
                done++
                hooks.progress(done, total)
                continue
            }
            try {
                engine.downloader.download(file.url, staged, token)
            } catch (e: MediaFetchException) {
                if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
                return MediaOutcome.Failed(mediaErrorInfo(e.failure, req.url, hasCookies))
            }
            if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
            done++
            hooks.progress(done, total)
        }

        // -- song snippet and video ------------------------------------------
        var note: String? = null
        if (single) {
            val base = bases.getValue(post0)
            val visuals = post0.items.mapNotNull { item ->
                val f = File(req.dir, mediaFileName(base, item))
                if (f.isFile) Visual(f, item.kind, item.width, item.height) else null
            }
            val songFile = planned.firstOrNull { it.isSong }?.let { File(req.dir, it.stagedName) }
            val result = convertStaging(
                dir = req.dir,
                post = post0,
                base = base,
                songFull = songFile,
                visuals = visuals,
                session = session,
                existingMix = mixPresent,
                onConvert = { hooks.converting() },
                makeVideo = req.photoMode == PhotoMode.PhotosSongVideo,
                cutSong = req.songLength == SongLength.Snippet,
            )
            if (result.cancelled || token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
            note = result.note
            if (mixExpected && result.video == null) total -= 1 // the mp4 was not made: keep the count honest
        } else {
            // A tray holds several unrelated songs: each is kept whole under its final name.
            for (file in planned.filter { it.isSong }) {
                val full = File(req.dir, file.stagedName)
                if (full.isFile) full.renameTo(File(req.dir, songName(bases.getValue(file.post), file.post, full.extension.ifEmpty { "m4a" })))
            }
        }

        // -- move to the output folder, archive ------------------------------
        val keys = HashMap<String, Pair<String, String>>()
        planned.forEach { keys[it.marker] = it.key }
        posts.forEach { keys["${it.id}_mix"] = MediaKeys.mix(it) }
        val finished = req.dir.listFiles()
            ?.filter { it.isFile && !it.name.startsWith(".") && !it.name.endsWith(".part") && " full [" !in it.name }
            ?.filter { markerOf(it.name) in keys }
            ?.sortedBy { it.name }
            .orEmpty()
        var created = 0
        var existing = 0
        var first: String? = null
        for (file in finished) {
            if (token.cancelled || hooks.stopped()) return MediaOutcome.Stopped
            val marker = markerOf(file.name)!!
            if (store.existsInFolder(owner, marker)) {
                existing++
                file.delete()
            } else {
                val published = try {
                    store.publish(file, file.name, owner)
                } catch (c: CancellationException) {
                    throw c
                } catch (_: StoragePermissionException) {
                    return MediaOutcome.Failed(STORAGE_PERMISSION)
                } catch (_: Exception) {
                    null
                } ?: return MediaOutcome.Failed(PUBLISH_FAILED)
                created++
                if (first == null) first = published.location
            }
            val (extractor, id) = keys.getValue(marker)
            try {
                archive.add(extractor, id)
            } catch (_: Exception) {
            }
        }
        cleanup(req.dir)
        return if (created > 0) {
            MediaOutcome.Done(first, note, total)
        } else {
            MediaOutcome.Skipped(ALREADY_SAVED_NOTE, total)
        }
    }

    /** Archived and still in the output folder. Archived but gone: the stale key is dropped so it downloads again. */
    private fun archivedAndPresent(file: Planned, owner: String?): Boolean {
        val (extractor, id) = file.key
        return try {
            if (!archive.has(extractor, id)) return false
            if (store.existsInFolder(owner, file.marker)) return true
            archive.remove(extractor, id)
            false
        } catch (_: Exception) {
            false
        }
    }

    private fun titleOf(post: MediaPost, owner: String?): String? {
        val line = post.caption?.lineSequence()?.firstOrNull { it.isNotBlank() }?.trim()?.take(100)
        if (!line.isNullOrEmpty()) return line
        val parts = listOfNotNull(owner ?: post.owner, post.id).filter { it.isNotBlank() }
        return parts.joinToString(" ").ifEmpty { null }
    }

    private fun cleanup(dir: File) {
        try {
            dir.listFiles()?.forEach { if (it.isFile) it.delete() }
            dir.delete()
        } catch (_: Exception) {
        }
    }
}
