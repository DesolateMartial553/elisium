package com.desolate.elisium.settings

/**
 * What an imported file turned out to be. A phone cannot read a browser's cookie store, so
 * Elisium takes a `cookies.txt` file exported on a computer instead.
 */
sealed interface CookiesCheck {
    /** A readable Netscape cookie file holding [count] cookies. */
    data class Valid(val count: Int) : CookiesCheck

    /** A cookies.txt with a header but no cookies in it (or an empty file). */
    data object Empty : CookiesCheck

    /** Not a cookie file at all (an HTML page, JSON, a random text file). */
    data object WrongFormat : CookiesCheck
}

/** What Settings shows about the imported file. The file itself is the only source of truth. */
sealed interface CookiesStatus {
    data object None : CookiesStatus
    data class Imported(val count: Int) : CookiesStatus
}

const val COOKIES_HEADER = "# Netscape HTTP Cookie File"
const val COOKIES_HEADER_ALT = "# HTTP Cookie File"

/**
 * Checks that [text] looks like a Netscape cookie file: the magic header line, or tab-separated
 * rows of the seven fields yt-dlp reads (domain, include-subdomains, path, secure, expiry, name,
 * value). Comments and blank lines are ignored. Pure, so the rules are JVM-tested.
 */
fun checkCookiesFile(text: String?): CookiesCheck {
    if (text == null) return CookiesCheck.Empty
    val body = text.removePrefix("\uFEFF")
    if (body.isBlank()) return CookiesCheck.Empty
    if (body.trimStart().startsWith("<")) return CookiesCheck.WrongFormat // an HTML page saved as cookies.txt

    var header = false
    var count = 0
    for (raw in body.lineSequence()) {
        val line = raw.trimEnd('\r')
        if (line.isBlank()) continue
        if (line.startsWith("#")) {
            val start = line.take(40).lowercase()
            if (start.startsWith("# netscape http cookie file") || start.startsWith("# http cookie file")) {
                header = true
            }
            continue
        }
        if (isCookieRow(line)) count++
    }
    return when {
        count > 0 -> CookiesCheck.Valid(count)
        header -> CookiesCheck.Empty
        else -> CookiesCheck.WrongFormat
    }
}

/** One data row: exactly seven tab-separated fields with a domain, a TRUE/FALSE flag and a name. */
private fun isCookieRow(line: String): Boolean {
    val fields = line.split('\t')
    if (fields.size != 7) return false
    val domain = fields[0].trim()
    val includeSubdomains = fields[1].trim()
    val name = fields[5].trim()
    return domain.isNotEmpty() &&
        (includeSubdomains.equals("TRUE", ignoreCase = true) || includeSubdomains.equals("FALSE", ignoreCase = true)) &&
        name.isNotEmpty()
}
