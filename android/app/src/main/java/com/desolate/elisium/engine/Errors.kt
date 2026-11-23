package com.desolate.elisium.engine

/** A user-facing explanation of a failed download (port of `errors.py`). */
data class ErrorInfo(val message: String, val fix: String, val code: String)

private val FALLBACK = ErrorInfo("Download failed.", "See Details", "unknown")

private const val CAUSE_MAX = 200
private const val REMOVED = "[removed]"
private val HEADER_LINE = Regex("(?i)\\b(set-cookie|cookie|authorization|proxy-authorization|x-csrftoken)\\s*[:=][^\\n]*")
private val SECRET_PAIR = Regex(
    "(?i)\\b(sessionid|csrftoken|ds_user_id|ig_did|mid|rur|datr|sid|token|access_token|auth\\w*|password|secret)\\s*[=:]\\s*[^\\s;,&\"']+",
)
private val COOKIE_TAB = Regex("(?i)\\b(sessionid|csrftoken|ds_user_id|ig_did|mid|rur|datr|sid)\\t[^\\t\\n]*")
private val BEARER = Regex("(?i)\\b(bearer|basic)\\s+[A-Za-z0-9._~+/=-]+")
private val LONG_TOKEN = Regex("[A-Za-z0-9%_-]{32,}")

/**
 * A short, safe description of why something failed, for the item's Details line: the exception class
 * name plus its message, with anything that looks like a cookie value, a Cookie/Authorization header
 * or a long opaque token removed, whitespace collapsed and the whole text cut to 200 characters.
 */
fun sanitizeCause(error: Throwable): String =
    sanitizeCauseText("${error.javaClass.simpleName.ifEmpty { "Error" }}: ${error.message.orEmpty()}")

/** The same cleaning for plain text (a yt-dlp error line): redact, collapse, truncate to 200 characters. */
fun sanitizeCauseText(text: String?): String {
    var out = COOKIE_TAB.replace(text ?: "", "$1 $REMOVED").replace('\t', ' ')
    out = HEADER_LINE.replace(out, REMOVED)
    out = SECRET_PAIR.replace(out) { "${it.groupValues[1]}=$REMOVED" }
    out = BEARER.replace(out, REMOVED)
    out = LONG_TOKEN.replace(out, REMOVED)
    out = out.replace(Regex("\\s+"), " ").trim()
    return if (out.length > CAUSE_MAX) out.take(CAUSE_MAX - 3).trimEnd() + "..." else out
}

/** The last non-blank line of a log, for a Details line (the final `ERROR:` line is the useful one). */
fun lastLogLine(log: String?): String =
    (log ?: "").lineSequence().map { it.trim() }.lastOrNull { it.isNotEmpty() }.orEmpty()

/**
 * Keeps the user wording and the `unknown` code, and adds the sanitised cause to the line the row shows
 * after the message ("Download failed. See Details: IllegalStateException: ..."). A blank [cause] changes nothing.
 */
fun withCause(info: ErrorInfo, cause: String?): ErrorInfo {
    if (info.code != "unknown") return info
    val clean = sanitizeCauseText(cause)
    return if (clean.isEmpty()) info else info.copy(fix = "${info.fix}: $clean")
}

// Instagram wording (used when there is no URL to judge, or it is Instagram).
internal val IG_SIGNED_IN = ErrorInfo(
    "Instagram needs you signed in.",
    "Sign in to Instagram in Settings > Accounts",
    "login_required",
)
// The site wants a sign-in but is not Instagram: same code, no site name.
private val SIGNED_IN = ErrorInfo("The site wants you to be signed in.", IG_SIGNED_IN.fix, "login_required")
internal val IG_RATE = ErrorInfo(
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

// Media engine (photo posts, stories, slideshows): same words as the desktop `errors.py`.
val STORY_EXPIRED = ErrorInfo(
    "This story has expired. Stories last 24 hours.",
    "Check the link",
    "story_expired",
)
val PRIVATE_ACCOUNT = ErrorInfo(
    "This account is private. Follow it in your browser, then sign in here.",
    "Follow the account in your browser, then sign in in Settings > Accounts",
    "private_account",
)

/** The media engine ran and found nothing it could save (no error text to go on). */
val NO_MEDIA_FILES = ErrorInfo(
    "There are no photos or videos to download here.",
    "Check the link",
    "no_media",
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
    // yt-dlp wording for an anonymous request that Instagram sent to its login page.
    listOf(
        "redirected to the login page",
        "rate-limit for accessing posts anonymously",
        "only available for registered users",
        "rate-limit reached or login required",
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
