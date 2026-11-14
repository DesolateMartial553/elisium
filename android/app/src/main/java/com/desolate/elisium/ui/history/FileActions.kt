package com.desolate.elisium.ui.history

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
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
