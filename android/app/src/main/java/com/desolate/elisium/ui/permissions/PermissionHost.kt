package com.desolate.elisium.ui.permissions

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.core.content.ContextCompat
import com.desolate.elisium.R
import kotlinx.coroutines.flow.Flow

/** Remembers which permissions were already asked about (once each, ever). */
private class PermissionPrefs(context: Context) {
    private val prefs = context.getSharedPreferences("permission_prefs", Context.MODE_PRIVATE)
    fun asked(kind: PermissionKind) = prefs.getBoolean(kind.name, false)
    fun markAsked(kind: PermissionKind) = prefs.edit().putBoolean(kind.name, true).apply()
}

private fun granted(context: Context, permission: String) =
    ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

/**
 * After the first link is added, explains in one line why a permission helps and then asks.
 * Links are already queued by then: a "no" (or no answer) never stops downloads, it only means
 * no notifications / a failed save on Android 8-9. Compile-verified only.
 */
@Composable
fun PermissionHost(linksAdded: Flow<Int>) {
    val context = LocalContext.current
    val prefs = remember { PermissionPrefs(context) }
    var pending by remember { mutableStateOf<PermissionKind?>(null) }

    val notificationLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val storageLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }

    LaunchedEffect(linksAdded) {
        linksAdded.collect {
            if (pending != null) return@collect
            val facts = PermissionFacts(
                sdk = Build.VERSION.SDK_INT,
                notificationsGranted = Build.VERSION.SDK_INT < 33 ||
                    granted(context, Manifest.permission.POST_NOTIFICATIONS),
                notificationsAsked = prefs.asked(PermissionKind.Notifications),
                storageGranted = granted(context, Manifest.permission.WRITE_EXTERNAL_STORAGE),
                storageAsked = prefs.asked(PermissionKind.Storage),
            )
            pending = nextPermissionToAsk(facts)
        }
    }

    val kind = pending ?: return
    AlertDialog(
        onDismissRequest = {
            prefs.markAsked(kind)
            pending = null
        },
        text = { Text(stringResource(rationaleRes(kind))) },
        confirmButton = {
            TextButton(onClick = {
                prefs.markAsked(kind)
                pending = null
                when (kind) {
                    PermissionKind.Notifications ->
                        if (Build.VERSION.SDK_INT >= 33) notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    PermissionKind.Storage -> storageLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                }
            }) { Text(stringResource(R.string.perm_continue)) }
        },
        dismissButton = {
            TextButton(onClick = {
                prefs.markAsked(kind)
                pending = null
            }) { Text(stringResource(R.string.perm_not_now)) }
        },
    )
}
