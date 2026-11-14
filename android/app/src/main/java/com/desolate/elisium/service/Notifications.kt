package com.desolate.elisium.service

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.desolate.elisium.MainActivity

const val CHANNEL_DOWNLOADS = "downloads"
const val CHANNEL_RESULTS = "download_results"
const val ONGOING_ID = 1001
const val RESULT_ID = 1002

/** Builds and posts the notifications. Android-bound: compile-verified only (the text comes from the tested `QueueSummary.kt`). */
object Notifications {
    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_DOWNLOADS, "Downloads", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Progress of running downloads"
                setShowBadge(false)
            },
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_RESULTS, "Finished downloads", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "When downloads finish or fail"
            },
        )
    }

    private fun openApp(context: Context): PendingIntent = PendingIntent.getActivity(
        context, 0,
        Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun serviceAction(context: Context, action: String, code: Int): PendingIntent = PendingIntent.getService(
        context, code,
        Intent(context, DownloadService::class.java).setAction(action),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    fun ongoing(context: Context, model: NotificationModel) = NotificationCompat.Builder(context, CHANNEL_DOWNLOADS)
        .setSmallIcon(android.R.drawable.stat_sys_download)
        .setContentTitle(model.title)
        .setContentText(model.text)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setCategory(NotificationCompat.CATEGORY_PROGRESS)
        .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        .setContentIntent(openApp(context))
        .addAction(0, "Pause all", serviceAction(context, DownloadService.ACTION_PAUSE_ALL, 1))
        .addAction(0, "Cancel all", serviceAction(context, DownloadService.ACTION_CANCEL_ALL, 2))
        .apply {
            val percent = model.progressPercent
            if (percent != null) setProgress(100, percent, false) else if (model.indeterminate) setProgress(0, 0, true)
        }
        .build()

    fun postOngoing(context: Context, model: NotificationModel) = post(context, ONGOING_ID, ongoing(context, model))

    fun postCompletion(context: Context, summary: BatchSummary) {
        val (title, text) = completionText(summary)
        val notification = NotificationCompat.Builder(context, CHANNEL_RESULTS)
            .setSmallIcon(
                if (summary.failed > 0) android.R.drawable.stat_notify_error else android.R.drawable.stat_sys_download_done,
            )
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(openApp(context))
            .build()
        post(context, RESULT_ID, notification)
    }

    private fun post(context: Context, id: Int, notification: android.app.Notification) {
        val granted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        if (!granted) return
        NotificationManagerCompat.from(context).notify(id, notification)
    }
}
