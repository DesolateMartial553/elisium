package com.desolate.elisium.storage

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.annotation.RequiresApi
import com.desolate.elisium.engine.OutputStore
import com.desolate.elisium.engine.PublishedFile
import com.desolate.elisium.engine.StoragePermissionException
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Staging -> public folder copy buffer: 1 MiB (Kotlin's `copyTo` default is 8 KiB, many more system calls on a big video). */
private const val COPY_BUFFER_BYTES = 1 shl 20

/**
 * [OutputStore] that moves finished files into `Download/Elisium/`.
 *
 * API 29+: MediaStore.Downloads with IS_PENDING while copying. API 26-28: straight into the
 * public Downloads folder (needs WRITE_EXTERNAL_STORAGE, requested by the UI in 5D) plus a
 * media-scanner pass. The decisions (names, MIME, skip-if-exists) live in `OutputNaming.kt`
 * and are JVM-tested; this class is only the thin Android calls and is compile-verified only.
 */
class MediaStoreOutputStore(context: Context) : OutputStore {
    private val appContext = context.applicationContext
    private val resolver get() = appContext.contentResolver

    // -- queries ---------------------------------------------------------
    override fun existsFor(extractorKey: String, videoId: String): Boolean = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) existingByIdModern(videoId) else existingByIdLegacy(videoId)
    } catch (_: Exception) {
        false
    }

    /** Is a file whose name contains `[<videoId>]` already in the owner's [subfolder] (flat when null)? */
    override fun existsInFolder(subfolder: String?, videoId: String): Boolean = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            existingByIdModern(videoId, relativePathFor(subfolder))
        } else {
            existingByIdLegacy(videoId, subfolder)
        }
    } catch (_: Exception) {
        false
    }

    override fun existsAt(location: String): Boolean = try {
        if (location.startsWith("content://")) {
            resolver.query(Uri.parse(location), arrayOf(MediaStore.MediaColumns._ID), null, null, null)
                ?.use { it.count > 0 } ?: false
        } else {
            File(location).isFile
        }
    } catch (_: Exception) {
        // Cannot tell: the contract says unknown means present, so a transient error never re-downloads.
        true
    }

    /** No bookkeeping is kept beyond the files themselves. */
    override fun forget(extractorKey: String, videoId: String) = Unit

    // -- publishing ------------------------------------------------------
    override suspend fun publish(stagedFile: File, displayName: String): PublishedFile? =
        publish(stagedFile, displayName, null)

    /** Media engine files land in `Download/Elisium/<owner>/`; a null or blank [subfolder] stays flat. */
    override suspend fun publish(stagedFile: File, displayName: String, subfolder: String?): PublishedFile? =
        withContext(Dispatchers.IO) {
            val name = safeDisplayName(displayName)
            if (!stagedFile.isFile) return@withContext null
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    publishModern(stagedFile, name, relativePathFor(subfolder))
                } else {
                    publishLegacy(stagedFile, name, subfolder)
                }
            } catch (c: CancellationException) {
                throw c
            } catch (p: StoragePermissionException) {
                throw p
            } catch (_: Exception) {
                null
            }
        }

    override fun delete(location: String): Boolean = try {
        if (location.startsWith("content://")) resolver.delete(Uri.parse(location), null, null) > 0 else File(location).delete()
    } catch (_: Exception) {
        false
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun publishModern(staged: File, name: String, relativePath: String): PublishedFile? {
        val existing = findModernByName(name, relativePath)
        if (decidePublish(existing != null) == PublishDecision.USE_EXISTING) {
            staged.delete()
            return PublishedFile(existing.toString(), name)
        }
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, mimeTypeFor(name))
            put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
        try {
            val out = resolver.openOutputStream(uri) ?: throw java.io.IOException("no output stream")
            out.use { sink -> staged.inputStream().use { it.copyTo(sink, COPY_BUFFER_BYTES) } }
            val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
            resolver.update(uri, done, null, null)
        } catch (e: Throwable) {
            try {
                resolver.delete(uri, null, null)
            } catch (_: Exception) {
            }
            if (e is CancellationException) throw e
            return null
        }
        staged.delete()
        return PublishedFile(uri.toString(), name)
    }

    @Suppress("DEPRECATION")
    private fun legacyDir(subfolder: String? = null): File =
        File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), folderPathFor(subfolder))

    private fun publishLegacy(staged: File, name: String, subfolder: String?): PublishedFile? {
        // API 26-28 needs WRITE_EXTERNAL_STORAGE; without it mkdirs fails and the real cause would be hidden.
        if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            throw StoragePermissionException()
        }
        val dir = legacyDir(subfolder)
        if (!dir.isDirectory && !dir.mkdirs()) return null
        val target = File(dir, name)
        if (decidePublish(target.isFile) == PublishDecision.USE_EXISTING) {
            staged.delete()
            return PublishedFile(target.path, name)
        }
        val temp = File(dir, "$name.elisium-tmp")
        try {
            staged.inputStream().use { input -> temp.outputStream().use { input.copyTo(it, COPY_BUFFER_BYTES) } }
            if (!temp.renameTo(target)) throw java.io.IOException("rename failed")
        } catch (e: Throwable) {
            temp.delete()
            target.takeIf { !it.isFile }?.delete()
            if (e is CancellationException) throw e
            return null
        }
        staged.delete()
        MediaScannerConnection.scanFile(appContext, arrayOf(target.path), arrayOf(mimeTypeFor(name)), null)
        return PublishedFile(target.path, name)
    }

    // -- lookups ---------------------------------------------------------
    private val modernProjection = arrayOf(MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME)

    /** The content URI of a file with exactly [name] in [relativePath] (Download/Elisium/ or an owner folder), or null. */
    @RequiresApi(Build.VERSION_CODES.Q)
    private fun findModernByName(name: String, relativePath: String): Uri? {
        val cursor = resolver.query(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            modernProjection,
            "${MediaStore.MediaColumns.DISPLAY_NAME} = ? AND ${MediaStore.MediaColumns.RELATIVE_PATH} = ?",
            arrayOf(name, relativePath),
            null,
        ) ?: return null
        cursor.use {
            if (!it.moveToFirst()) return null
            return ContentUris.withAppendedId(MediaStore.Downloads.EXTERNAL_CONTENT_URI, it.getLong(0))
        }
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun existingByIdModern(videoId: String, relativePath: String = RELATIVE_PATH): Boolean {
        val cursor = resolver.query(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            modernProjection,
            "${MediaStore.MediaColumns.DISPLAY_NAME} LIKE ? ESCAPE '\\' AND ${MediaStore.MediaColumns.RELATIVE_PATH} = ?",
            arrayOf(likePatternForVideoId(videoId), relativePath),
            null,
        ) ?: return false
        cursor.use {
            while (it.moveToNext()) {
                if (nameHasVideoId(it.getString(1).orEmpty(), videoId)) return true
            }
        }
        return false
    }

    private fun existingByIdLegacy(videoId: String, subfolder: String? = null): Boolean {
        val dir = legacyDir(subfolder)
        val names = dir.list() ?: return false
        return names.any { nameHasVideoId(it, videoId) && File(dir, it).isFile }
    }
}
