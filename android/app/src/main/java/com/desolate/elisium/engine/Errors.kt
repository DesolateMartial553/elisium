package com.desolate.elisium.engine

/** A user-facing explanation of a failed download (port of `errors.py`). */
data class ErrorInfo(val message: String, val fix: String, val code: String)

private val FALLBACK = ErrorInfo("Download failed.", "See Details", "unknown")

// Order matters: first match wins (same order as the spec table).
private val TABLE: List<Pair<List<String>, ErrorInfo>> = listOf(
    listOf("sign in to confirm", "not a bot") to
        ErrorInfo("The site wants you to be signed in.", "Import cookies", "sign_in_required"),
    // Instagram stories and private posts print this without cookies. Android has no browser
    // access, so the fix points at the cookies.txt import in Settings > Accounts.
    listOf(
        "you need to log in to access this content",
        "log in to view this content",
        "you must be logged in to view",
        "instagram needs you signed in",
    ) to
        ErrorInfo("Instagram needs you signed in.", "Import cookies in Settings > Accounts", "login_required"),
    // Instagram's own pacing message, not a plain HTTP 429.
    listOf("please wait a few minutes", "instagram is limiting", "request limit reached") to
        ErrorInfo(
            "Instagram is limiting requests. Wait a few minutes and try again.",
            "Wait a few minutes and try again",
            "rate_limited",
        ),
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
            "Import cookies.txt again in Settings > Accounts",
            "cookies_unreadable",
        ),
    listOf("video unavailable", "private video") to
        ErrorInfo("This video is not available.", "Check the link", "video_unavailable"),
    listOf("requested format is not available") to
        ErrorInfo("That quality isn't offered for this video.", "Pick another format", "format_unavailable"),
    listOf("http error 403") to
        ErrorInfo("The site refused the download.", "Update yt-dlp, or import cookies", "http_403"),
    listOf("http error 429") to
        ErrorInfo("Too many requests.", "Wait, lower concurrency", "http_429"),
    listOf("unable to download", "timed out", "timeout", "connection") to
        ErrorInfo("Network problem.", "Retry (auto-retry already ran)", "network"),
    listOf("ffmpeg not found", "ffmpeg is not installed") to
        ErrorInfo("ffmpeg is missing.", "Install ffmpeg", "ffmpeg_missing"),
)

/** Maps [rawLog] to an [ErrorInfo]: case-insensitive substring, first match wins. */
fun explain(rawLog: String?): ErrorInfo {
    val text = (rawLog ?: "").lowercase()
    for ((needles, info) in TABLE) {
        if (needles.any { text.contains(it) }) return info
    }
    return FALLBACK
}
