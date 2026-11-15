package com.desolate.elisium.engine

/** A user-facing explanation of a failed download (port of `errors.py`). */
data class ErrorInfo(val message: String, val fix: String, val code: String)

private val FALLBACK = ErrorInfo("Download failed.", "See Details", "unknown")

// Instagram wording (used when there is no URL to judge, or it is Instagram).
private val IG_SIGNED_IN = ErrorInfo(
    "Instagram needs you signed in.",
    "Sign in to Instagram in Settings > Accounts",
    "login_required",
)
// The site wants a sign-in but is not Instagram: same code, no site name.
private val SIGNED_IN = ErrorInfo("The site wants you to be signed in.", IG_SIGNED_IN.fix, "login_required")
private val IG_RATE = ErrorInfo(
    "Instagram is limiting requests. Wait a few minutes and try again.",
    "Wait a few minutes and try again",
    "rate_limited",
)
private val RATE_LIMITED = ErrorInfo("The site is limiting requests. Wait a few minutes and try again.", IG_RATE.fix, "rate_limited")
// An imported cookies.txt is in place and Instagram still asked for a sign-in: the session has gone stale.
private val SESSION_EXPIRED = ErrorInfo(
    "Your Instagram sign-in has expired.",
    "Sign in to Instagram in Settings > Accounts",
    "session_expired",
)

// Order matters: first match wins (same order as the spec table).
private val TABLE: List<Pair<List<String>, ErrorInfo>> = listOf(
    listOf("sign in to confirm", "not a bot") to
        ErrorInfo("The site wants you to be signed in.", "Import cookies", "sign_in_required"),
    // Instagram stories and private posts print this without a signed-in session. The fix points at
    // the in-app sign-in on Instagram's own page (Settings > Accounts).
    listOf(
        "you need to log in to access this content",
        "log in to view this content",
        "you must be logged in to view",
        "instagram needs you signed in",
    ) to IG_SIGNED_IN,
    // Instagram's own pacing message, not a plain HTTP 429.
    listOf("please wait a few minutes", "instagram is limiting", "request limit reached") to IG_RATE,
    // A post with no video: yt-dlp's own wording (extractor/instagram.py, raise_no_formats
    // and the empty Polaris response).
    listOf("there is no video in this post", "instagram sent an empty media response") to
        ErrorInfo("This post has no video to download.", "Check the link", "no_media"),
    // The imported cookies.txt could not be used (unreadable, or no longer a valid session).
    listOf(
        "could not find cookies database",
        "failed to decrypt",
        "could not copy chrome cookie database",
        "could not find firefox cookies database",
        "not a netscape format cookie file",
        "netscape format cookies file",
        "cookies are no longer valid",
    ) to
        ErrorInfo(
            "Elisium could not read those cookies.",
            "Sign in to Instagram in Settings > Accounts",
            "cookies_unreadable",
        ),
    listOf("video unavailable", "private video") to
        ErrorInfo("This video is not available.", "Check the link", "video_unavailable"),
    listOf("requested format is not available") to
        ErrorInfo("That quality isn't offered for this video.", "Pick another format", "format_unavailable"),
    listOf("http error 401") to
        ErrorInfo("The site refused to let Elisium in.", "Sign in, then try again", "http_401"),
    listOf("http error 403") to
        ErrorInfo("The site refused the download.", "Update yt-dlp in Settings, or sign in", "http_403"),
    listOf("http error 429") to
        ErrorInfo("Too many requests.", "Wait, lower concurrency", "http_429"),
    listOf("unable to download", "timed out", "timeout", "connection") to
        ErrorInfo("Network problem.", "Retry (auto-retry already ran)", "network"),
    listOf("ffmpeg not found", "ffmpeg is not installed") to
        ErrorInfo("ffmpeg is missing.", "Install ffmpeg", "ffmpeg_missing"),
)

/** True when a message may name Instagram: no URL, or an Instagram URL. */
private fun instagramOnly(url: String?): Boolean {
    if (url == null || url.isBlank()) return true
    return siteKind(url) == "instagram"
}

/**
 * Adjusts [info] for the item's site and cookie state.
 *
 * - `login_required` / `rate_limited` on a non-Instagram URL use the generic wording.
 * - `login_required` on Instagram with cookies configured is an expired session.
 *
 * [hasCookies] keeps its camelCase spelling so both platforms use the same argument name.
 */
fun applyContext(info: ErrorInfo, url: String? = null, hasCookies: Boolean = false): ErrorInfo =
    when (info.code) {
        "login_required" ->
            if (instagramOnly(url)) {
                if (hasCookies) SESSION_EXPIRED else info
            } else {
                SIGNED_IN
            }
        "rate_limited" -> if (instagramOnly(url)) info else RATE_LIMITED
        else -> info
    }

/** Maps [rawLog] to an [ErrorInfo]: case-insensitive substring, first match wins. */
fun explain(rawLog: String?, url: String? = null, hasCookies: Boolean = false): ErrorInfo {
    val text = (rawLog ?: "").lowercase()
    for ((needles, info) in TABLE) {
        if (needles.any { text.contains(it) }) return applyContext(info, url, hasCookies)
    }
    return FALLBACK
}
