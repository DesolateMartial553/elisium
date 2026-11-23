package com.desolate.elisium.ui.settings

import com.desolate.elisium.engine.sanitizeCauseText

/*
 * Plain-words reasons for a sign-in page that did not load. Pure so the JVM can test them; the numbers are
 * `WebViewClient.ERROR_*` values (written out so no Android class is needed here).
 */

/** Longest raw description kept when the code has no friendlier wording. */
private const val DESCRIPTION_MAX = 60

/** A short reason for a main-frame load error ([errorCode] from `onReceivedError`, [description] its text). */
fun loginErrorReason(errorCode: Int, description: CharSequence?): String = when (errorCode) {
    -2 -> "could not find Instagram" // ERROR_HOST_LOOKUP
    -6, -7 -> "could not connect" // ERROR_CONNECT, ERROR_IO
    -8 -> "timed out" // ERROR_TIMEOUT
    -11, -12 -> "secure connection failed" // ERROR_FAILED_SSL_HANDSHAKE, ERROR_BAD_URL
    -15 -> "too many requests" // ERROR_TOO_MANY_REQUESTS
    else -> {
        val text = sanitizeCauseText(description?.toString()).removePrefix("net::").take(DESCRIPTION_MAX).trim()
        text.ifEmpty { "error $errorCode" }
    }
}

/** A short reason for a main-frame HTTP error (status 400 or more). */
fun loginHttpReason(status: Int): String = when {
    status == 429 -> "Instagram says too many requests"
    status == 403 || status == 401 -> "Instagram refused the request (HTTP $status)"
    status == 404 -> "page not found (HTTP 404)"
    status >= 500 -> "Instagram had a problem (HTTP $status)"
    else -> "HTTP $status"
}

/** True when an HTTP status on the main frame should show the "did not load" message. */
fun loginHttpIsFailure(status: Int): Boolean = status >= 400
