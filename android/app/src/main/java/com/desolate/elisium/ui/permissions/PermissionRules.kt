package com.desolate.elisium.ui.permissions

import androidx.annotation.StringRes
import com.desolate.elisium.R

enum class PermissionKind { Notifications, Storage }

/** What the app knows when a link is added. [sdk] is `Build.VERSION.SDK_INT`. */
data class PermissionFacts(
    val sdk: Int,
    val notificationsGranted: Boolean,
    val notificationsAsked: Boolean,
    val storageGranted: Boolean,
    val storageAsked: Boolean,
)

private const val API_TIRAMISU = 33
private const val API_P = 28
private const val API_OREO = 26

/** Notifications need a runtime permission from Android 13 (API 33) up. */
fun shouldAskNotifications(f: PermissionFacts): Boolean =
    f.sdk >= API_TIRAMISU && !f.notificationsGranted && !f.notificationsAsked

/** Public-folder writes need WRITE_EXTERNAL_STORAGE on Android 8 and 9 only (API 26-28). */
fun shouldAskStorage(f: PermissionFacts): Boolean =
    f.sdk in API_OREO..API_P && !f.storageGranted && !f.storageAsked

/** The one permission to explain and request now, or null. Each is asked at most once; adding links is never blocked. */
fun nextPermissionToAsk(f: PermissionFacts): PermissionKind? = when {
    shouldAskStorage(f) -> PermissionKind.Storage
    shouldAskNotifications(f) -> PermissionKind.Notifications
    else -> null
}

/** The one-line reason shown before the system dialog. */
@StringRes
fun rationaleRes(kind: PermissionKind): Int = when (kind) {
    PermissionKind.Notifications -> R.string.perm_notifications_reason
    PermissionKind.Storage -> R.string.perm_storage_reason
}

/** Settings shows the gentle "notifications are off" line when Android reports them disabled for the app. */
fun showNotificationsOffNotice(notificationsEnabled: Boolean): Boolean = !notificationsEnabled
