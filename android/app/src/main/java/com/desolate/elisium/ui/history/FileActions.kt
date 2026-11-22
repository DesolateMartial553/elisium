package com.desolate.elisium.ui.history

import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File

/** Authority of the FileProvider declared in the manifest (needed for pre-Android-10 plain paths). */
fun fileProviderAuthority(context: Context) = "${context.packageName}.files"

/**
 * Opens a finished file with whatever app handles it. [location] is a `content://` URI (Android 10+)
 * or a plain path (Android 8-9). Returns false when nothing can open it. Compile-verified only.
 */
fun openFile(context: Context, location: String): Boolean {
    val uri: Uri
    val mime: String
    try {
        if (location.startsWith("content://")) {
            uri = Uri.parse(location)
            mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
        } else {
            uri = FileProvider.getUriForFile(context, fileProviderAuthority(context), File(location))
            mime = mimeForName(location)
        }
    } catch (_: IllegalArgumentException) {
        return false
    }
    val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(uri, mime)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    return try {
        context.startActivity(intent)
        true
    } catch (_: ActivityNotFoundException) {
        false
    }
}

/** Shares the original link as text through the system share sheet. */
fun shareLink(context: Context, url: String, chooserTitle: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, url)
    context.startActivity(Intent.createChooser(send, chooserTitle).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** The storage provider that serves the phone's own storage to the system Files app. */
const val EXTERNAL_STORAGE_AUTHORITY = "com.android.externalstorage.documents"

/** Document id of a folder on the phone's own storage: "primary:Download/Elisium/owner". */
fun folderDocumentId(relativePath: String): String = "primary:" + relativePath.trim('/')

/** Folder of a plain file path as a path below [storageRoot] ("Download/Elisium/owner"); null outside it. */
fun relativeFolderOfPath(path: String, storageRoot: String): String? {
    val root = storageRoot.trimEnd('/')
    if (!path.startsWith("$root/")) return null
    val parent = path.substringBeforeLast('/', "")
    return parent.removePrefix(root).trim('/').ifEmpty { null }
}

/** What "Open" does for a finished item: one file opens in its app, a photo post or story tray opens its folder. */
enum class OpenTarget { File, Folder }

fun openTargetFor(multiFile: Boolean): OpenTarget = if (multiFile) OpenTarget.Folder else OpenTarget.File

private fun tryStart(context: Context, intent: Intent): Boolean = try {
    context.startActivity(intent)
    true
} catch (_: Exception) {
    false
}

/** The folder a saved file lives in, as a path below the phone's storage root, or null when it cannot be found. */
private fun relativeFolderOf(context: Context, location: String): String? = try {
    if (location.startsWith("content://")) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            context.contentResolver.query(
                Uri.parse(location), arrayOf(MediaStore.MediaColumns.RELATIVE_PATH), null, null, null,
            )?.use { c -> if (c.moveToFirst()) c.getString(0)?.trim('/')?.ifEmpty { null } else null }
        } else {
            null
        }
    } else {
        @Suppress("DEPRECATION")
        relativeFolderOfPath(location, Environment.getExternalStorageDirectory().path)
    }
} catch (_: Exception) {
    null
}

/**
 * Shows the folder a finished file is in (the Files app); falls back to the system Downloads list.
 * Returns false when nothing could be opened. Compile-verified only.
 */
fun openFolder(context: Context, location: String): Boolean {
    val relative = relativeFolderOf(context, location)
    if (relative != null) {
        val uri = DocumentsContract.buildDocumentUri(EXTERNAL_STORAGE_AUTHORITY, folderDocumentId(relative))
        val view = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, DocumentsContract.Document.MIME_TYPE_DIR)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        if (tryStart(context, view)) return true
    }
    return tryStart(context, Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** "Open" for a finished item: the file for one file, the folder for a multi-file post. False when nothing could open it. */
fun openFinished(context: Context, location: String, multiFile: Boolean): Boolean =
    when (openTargetFor(multiFile)) {
        OpenTarget.Folder -> openFolder(context, location)
        OpenTarget.File -> openFile(context, location)
    }
