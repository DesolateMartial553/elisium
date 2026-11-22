package com.desolate.elisium.engine

import com.desolate.elisium.media.MediaRoute
import java.io.File
import java.net.URI
import java.nio.file.Files
import java.nio.file.StandardOpenOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/*
 * Pure rules for "Faster downloads" (brief 12D, mirrors desktop 12B/12C/12E): look a link up once and let the
 * download reuse that lookup, back off a site that answers 429, and show a steadier time left.
 * No Android types; everything here is JVM-tested.
 */

/** A probe older than this is looked up again (stream links expire). */
const val REUSE_PROBE_MAX_AGE_MS = 300_000L

/** EMA weight of the newest speed sample, and the quiet start of a file that is kept out of the average. */
const val SPEED_EMA_ALPHA = 0.2
const val SPEED_EMA_WARMUP_MS = 2_000L

internal val SIGNED_IN_SITES = setOf("instagram.com", "tiktok.com")
private val SITE_ALIASES = mapOf("youtu.be" to "youtube.com")
private val SECOND_LEVEL = setOf("co", "com", "org", "net", "ac", "gov")
private val RATE_LIMIT_CODES = setOf("http_429", "rate_limited")

/** Error codes that mean "the saved lookup is stale": the download is run once more from the link. */
private val STALE_INFO_CODES = setOf("http_403", "http_410", "format_unavailable")
private val STALE_INFO_WORDS = listOf("http error 403", "http error 410", "expired", "format is not available", "format not available")

/** A stable per-site key: `www.youtube.com` and `youtu.be` -> `youtube.com`; "" when the link has no host. */
fun siteKey(url: String?): String {
    var host = runCatching { URI(url.orEmpty().trim()).host }.getOrNull()?.lowercase()?.trimEnd('.').orEmpty()
    val labels = host.split('.')
    if (labels.size > 2) {
        val keep = if (labels.last().length == 2 && labels[labels.size - 2] in SECOND_LEVEL) 3 else 2
        host = labels.takeLast(keep).joinToString(".")
    }
    return SITE_ALIASES[host] ?: host
}

/** True when [code] is the site asking us to slow down (429 / "please wait"). */
fun isRateLimitCode(code: String?): Boolean = code != null && code in RATE_LIMIT_CODES

/**
 * Whether a probe's info may be loaded instead of looking the link up again: a JSON object that is not a
 * playlist or tray, with `formats` or `url`, probed less than [REUSE_PROBE_MAX_AGE_MS] ago.
 */
fun infoIsUsable(info: JsonObject?, ageMs: Long): Boolean {
    if (info == null || ageMs < 0 || ageMs >= REUSE_PROBE_MAX_AGE_MS) return false
    val type = (info["_type"] as? JsonPrimitive)?.takeIf { it.isString }?.content
    if (type == "playlist" || type == "multi_video") return false
    val formats = info["formats"] as? JsonArray
    val url = (info["url"] as? JsonPrimitive)?.takeIf { it.isString }?.content
    return !formats.isNullOrEmpty() || !url.isNullOrEmpty()
}

/**
 * May this download load the probe's info? Never when "Faster downloads" is Off, never for a media-engine
 * link, never for a site that answered 429 this session, never for a signed-in Instagram / TikTok link.
 */
fun mayReuseProbe(url: String, enabled: Boolean, route: MediaRoute, limitedSites: Set<String>, cookiesConfigured: Boolean): Boolean {
    if (!enabled || route == MediaRoute.MEDIA) return false
    val site = siteKey(url)
    if (site in limitedSites) return false
    return !(cookiesConfigured && site in SIGNED_IN_SITES)
}

/** False when [site] was rate limited and one of its downloads already runs (one at a time for that site). */
fun siteSlotFree(site: String, limitedSites: Set<String>, runningSites: List<String>): Boolean =
    site !in limitedSites || site !in runningSites

/**
 * After a download that used the saved lookup failed: run once more from the link (not a retry, no backoff)
 * when it failed before the first progress line, or the error says the lookup went stale.
 */
fun shouldRerunFromUrl(errorCode: String?, errorLog: String, sawProgress: Boolean): Boolean {
    if (!sawProgress) return true
    if (errorCode != null && errorCode in STALE_INFO_CODES) return true
    val text = errorLog.lowercase()
    return STALE_INFO_WORDS.any { it in text }
}

/**
 * Writes [info] to `<dir>/<name>` as a brand-new private file: an old file is removed first, the new one is
 * created with CREATE_NEW (never follows or overwrites a link), and only the owner can read or write it.
 */
fun writeInfoJson(dir: File, name: String, info: JsonObject): File {
    dir.mkdirs()
    val file = File(dir, name)
    file.delete()
    Files.newOutputStream(file.toPath(), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE).use {
        it.write(info.toString().toByteArray(Charsets.UTF_8))
    }
    file.setReadable(false, false)
    file.setWritable(false, false)
    file.setExecutable(false, false)
    file.setReadable(true, true)
    file.setWritable(true, true)
    return file
}

/** Why an item may sit at "Starting": the first reason that applies, else null. */
fun waitHint(rateLimited: Boolean, retryingNetwork: Boolean, signedIn: Boolean): String? = when {
    rateLimited -> WAIT_RATE_LIMITED
    retryingNetwork -> WAIT_NETWORK
    signedIn -> WAIT_SIGNING_IN
    else -> null
}

const val WAIT_RATE_LIMITED = "rate_limited"
const val WAIT_NETWORK = "network"
const val WAIT_SIGNING_IN = "signing_in"

/** True for the sites where a signed-in session is in play. */
fun isSignedInSite(url: String?): Boolean = siteKey(url) in SIGNED_IN_SITES

/** One exponential-moving-average step (the first sample seeds it). */
fun smoothSpeed(previous: Double?, sample: Double, alpha: Double = SPEED_EMA_ALPHA): Double =
    if (previous == null) sample else alpha * sample + (1.0 - alpha) * previous

/** Seconds left at the smoothed [speed], or null when it cannot be worked out. */
fun smoothedEta(totalBytes: Long?, downloadedBytes: Long?, speed: Double?): Double? {
    if (totalBytes == null || totalBytes <= 0 || downloadedBytes == null || speed == null || speed <= 0.0) return null
    return maxOf(0.0, (totalBytes - downloadedBytes) / speed)
}

/** The speed and time left a row shows. */
data class SmoothedProgress(val speed: Double?, val eta: Double?)

/**
 * Steadier speed and time left for one file: the first [SPEED_EMA_WARMUP_MS] of a file are shown as reported and kept
 * out of the average; afterwards speed is an EMA ([SPEED_EMA_ALPHA]) and time left is remaining / smoothed speed.
 * A byte count that drops (the next stream of the same item) starts the average again.
 */
class SpeedSmoother {
    private var startedAt: Long? = null
    private var average: Double? = null
    private var lastDownloaded: Long? = null

    fun update(nowMs: Long, downloaded: Long?, total: Long?, speed: Double?, eta: Double?): SmoothedProgress {
        val last = lastDownloaded
        if (downloaded != null && last != null && downloaded < last) {
            startedAt = null
            average = null
        }
        if (downloaded != null) lastDownloaded = downloaded
        val start = startedAt ?: nowMs.also { startedAt = it }
        if (nowMs - start < SPEED_EMA_WARMUP_MS) return SmoothedProgress(speed, eta)
        if (speed != null && speed > 0.0) average = smoothSpeed(average, speed)
        val avg = average ?: return SmoothedProgress(speed, eta)
        return SmoothedProgress(avg, smoothedEta(total, downloaded, avg) ?: eta)
    }
}
