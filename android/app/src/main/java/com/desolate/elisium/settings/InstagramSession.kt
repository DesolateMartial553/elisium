package com.desolate.elisium.settings

import java.net.URI

/**
 * The parts of an in-app Instagram sign-in that need no Android: reading the cookie header the
 * WebView's cookie store returns, deciding whether it holds a session, and writing that session as a
 * Netscape `cookies.txt` the engine already understands. Pure, so all of it is JVM-tested.
 */

/** The cookie only a completed sign-in leaves behind. */
const val INSTAGRAM_SESSION_COOKIE = "sessionid"

/** How long a captured session is written to last: one year (the cookie header carries no expiry). */
const val SESSION_LIFETIME_SECONDS = 31_536_000L

/** The domain written into every row. */
const val INSTAGRAM_COOKIE_DOMAIN = ".instagram.com"

/** Hosts the sign-in page may navigate to: Instagram itself, plus Facebook's sign-in frames and CDN. */
val LOGIN_ALLOWED_HOSTS: List<String> = listOf("instagram.com", "facebook.com", "fbcdn.net")

/**
 * Splits the `name=value; name2=value2` string `CookieManager.getCookie` returns. Blank entries and
 * entries without `=` are ignored; an `=` inside a value is kept (only the first one splits).
 */
fun parseCookieHeader(header: String?): List<Pair<String, String>> {
    if (header.isNullOrBlank()) return emptyList()
    val cookies = ArrayList<Pair<String, String>>()
    for (raw in header.split(';')) {
        val entry = raw.trim()
        if (entry.isEmpty()) continue
        val eq = entry.indexOf('=')
        if (eq <= 0) continue // no "=" at all, or an empty name
        val name = entry.substring(0, eq).trim()
        val value = entry.substring(eq + 1).trim()
        if (name.isEmpty()) continue
        cookies.add(name to value)
    }
    return cookies
}

/** True only when a `sessionid` cookie with a non-empty value is present. */
fun hasInstagramSession(header: String?): Boolean =
    parseCookieHeader(header).any { (name, value) -> name == INSTAGRAM_SESSION_COOKIE && value.isNotEmpty() }

/**
 * Writes [header] as a Netscape cookie file: the magic header line, then one seven-field row per
 * Instagram cookie (domain, include-subdomains, path, secure, expiry, name, value). A cookie whose
 * name or value holds a tab or a line break is dropped, so it cannot break the row.
 */
fun toNetscape(header: String, nowEpochSeconds: Long): String {
    val expiry = nowEpochSeconds + SESSION_LIFETIME_SECONDS
    val out = StringBuilder()
    out.append(COOKIES_HEADER).append('\n')
    for ((name, value) in parseCookieHeader(header)) {
        if (!fitsInARow(name) || !fitsInARow(value)) continue
        out.append(INSTAGRAM_COOKIE_DOMAIN).append('\t')
            .append("TRUE").append('\t')
            .append('/').append('\t')
            .append("TRUE").append('\t')
            .append(expiry).append('\t')
            .append(name).append('\t')
            .append(value).append('\n')
    }
    return out.toString()
}

/** A field may not contain the row and line separators of the Netscape format. */
private fun fitsInARow(field: String): Boolean = field.none { it == '\t' || it == '\n' || it == '\r' }

/**
 * The navigation guard: only `https` URLs on one of [LOGIN_ALLOWED_HOSTS] (or a subdomain of one)
 * may load. Everything else - `intent:`, `http:`, other sites - is blocked.
 */
fun loginHostAllowed(url: String?): Boolean {
    val raw = url?.trim().orEmpty()
    if (raw.isEmpty()) return false
    val uri = try {
        URI(raw)
    } catch (_: Exception) {
        return false
    }
    if (!uri.scheme.equals("https", ignoreCase = true)) return false
    val host = uri.host?.lowercase()?.trimEnd('.') ?: return false
    if (host.isEmpty()) return false
    return LOGIN_ALLOWED_HOSTS.any { allowed -> host == allowed || host.endsWith(".$allowed") }
}
