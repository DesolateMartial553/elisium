package com.desolate.elisium.backend

/** Minimum time between auto-update attempts: 24 hours in milliseconds. */
const val AUTO_UPDATE_INTERVAL_MS = 24L * 60 * 60 * 1000

/**
 * Pure policy for yt-dlp auto-update throttling.
 *
 * True only when:
 * - At least 24 h have passed since the last check (or lastCheckMs == 0, never checked).
 * - No download is active.
 * - Network condition matches settings (!wifiOnly || onWifi).
 * - The clock has not gone backwards past the last check (nowMs >= lastCheckMs); a manual update resets it.
 */
fun shouldAutoUpdate(
    nowMs: Long,
    lastCheckMs: Long,
    wifiOnly: Boolean,
    onWifi: Boolean,
    downloadsActive: Boolean,
): Boolean {
    if (downloadsActive) return false
    if (wifiOnly && !onWifi) return false
    if (lastCheckMs <= 0L) return true // never checked (the store never keeps a negative value)
    if (nowMs < lastCheckMs) return false
    return (nowMs - lastCheckMs) >= AUTO_UPDATE_INTERVAL_MS
}
