package com.desolate.elisium.media

import com.desolate.elisium.engine.ErrorInfo
import com.desolate.elisium.engine.IG_RATE
import com.desolate.elisium.engine.IG_SIGNED_IN
import com.desolate.elisium.engine.NO_MEDIA_FILES
import com.desolate.elisium.engine.PRIVATE_ACCOUNT
import com.desolate.elisium.engine.STORY_EXPIRED
import com.desolate.elisium.engine.applyContext
import com.desolate.elisium.engine.explain

private val VIDEO_UNAVAILABLE = ErrorInfo("This video is not available.", "Check the link", "video_unavailable")

/** True for `instagram.com/stories/...` links: a story that is gone is "expired", not "not available". */
private fun isStoryLink(url: String?): Boolean = when (classifyMediaUrl(url).kind) {
    MediaUrlKind.STORIES_USER, MediaUrlKind.STORY_ITEM, MediaUrlKind.HIGHLIGHT -> true
    else -> false
}

/**
 * The plain-words error for a media-engine failure (same wording as desktop `explain_gallery`):
 * a sign-in wall is `login_required` (or `session_expired` when cookies are set, generic wording off
 * Instagram), a rate limit is `rate_limited`, a missing or empty story is `story_expired`, a private
 * account is `private_account`, an empty non-story result is `no_media`, and an IO failure goes through
 * the yt-dlp table so it becomes the retried `network` code.
 */
fun mediaErrorInfo(failure: MediaFailure, url: String?, hasCookies: Boolean): ErrorInfo = when (failure) {
    MediaFailure.LOGIN_REQUIRED -> applyContext(IG_SIGNED_IN, url, hasCookies)
    MediaFailure.RATE_LIMITED -> applyContext(IG_RATE, url, hasCookies)
    MediaFailure.NOT_FOUND -> if (isStoryLink(url)) STORY_EXPIRED else VIDEO_UNAVAILABLE
    MediaFailure.PRIVATE -> PRIVATE_ACCOUNT
    MediaFailure.NO_MEDIA -> if (isStoryLink(url)) STORY_EXPIRED else NO_MEDIA_FILES
    MediaFailure.NETWORK -> explain("network problem: connection failed", url, hasCookies)
    MediaFailure.UNKNOWN -> explain("", url, hasCookies)
}
