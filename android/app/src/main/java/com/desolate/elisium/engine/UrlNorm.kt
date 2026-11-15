package com.desolate.elisium.engine

/**
 * URL normalisation and dedupe keys (port of `urlnorm.py`).
 *
 * Hand-parses URL and query like Python's `urlsplit` / `parse_qsl` / `urlencode`,
 * so results match the desktop engine byte for byte.
 */

private val YOUTUBE_HOSTS = setOf("youtube.com", "youtube-nocookie.com")
private const val SHORT_HOST = "youtu.be"
private val VIDEO_PATH_PREFIXES = setOf("shorts", "embed", "live", "v")
private val VIDEO_ID_RE = Regex("[A-Za-z0-9_-]+")
private val TIME_RE = Regex("(?:\\d+h)?(?:\\d+m)?(?:\\d+s)?")

private val TRACKING_PARAMS = setOf("si", "feature", "pp")

private const val INSTAGRAM_HOST = "instagram.com"

/** The TikTok short hosts are their own domain, so they are matched before any suffix rule. */
private val TIKTOK_HOSTS = setOf("tiktok.com", "vm.tiktok.com", "vt.tiktok.com")

/** Share links: the code alone identifies one video (never resolved, no network). */
private val TIKTOK_SHORT_HOSTS = setOf("vm.tiktok.com", "vt.tiktok.com")

// Share-link parameters added by the Instagram app / web share sheet. `img_index` is
// deliberately kept: it selects one image of a carousel post.
private val INSTAGRAM_DROP = setOf("igsh", "igshid")

// Share-link parameters added by the TikTok app and web share sheet.
private val TIKTOK_DROP = setOf(
    "_t",
    "_r",
    "is_from_webapp",
    "sender_device",
    "sender_web_id",
    "share_app_id",
    "share_link_id",
    "share_item_id",
    "source",
    "checksum",
    "refer",
    "region",
    "lang",
    "u_code",
    "timestamp",
    "user_id",
    "tt_from",
)

// Instagram post paths that carry a shortcode.
private val INSTAGRAM_POST_PREFIXES = setOf("p", "reel", "tv")

/** Python `str.isspace()` for the characters that matter here. */
internal fun isPySpace(c: Char): Boolean =
    c.isWhitespace() || c == '\u00a0' || c == '\u0085' || c == '\u2007' || c == '\u202f'

internal fun String.pyStrip(): String = this.trim { isPySpace(it) }

private class Parts(
    val scheme: String,
    val netloc: String,
    val path: String,
    val query: String,
) {
    private val hostInfo: String get() = netloc.substringAfterLast('@')
    private val hasUserInfo: Boolean get() = netloc.contains('@')

    val hostname: String?
        get() {
            val info = hostInfo
            val host = if (info.startsWith("[") && info.contains(']')) {
                info.substring(1, info.indexOf(']'))
            } else {
                info.substringBefore(':')
            }
            return if (host.isEmpty()) null else host.lowercase()
        }

    /** The port, or null; throws IllegalArgumentException for a bad port like Python. */
    val port: Int?
        get() {
            val info = hostInfo
            val text = if (info.startsWith("[") && info.contains(']')) {
                val rest = info.substring(info.indexOf(']') + 1)
                if (rest.startsWith(":")) rest.substring(1) else ""
            } else if (info.contains(':')) {
                info.substringAfter(':')
            } else {
                ""
            }
            if (text.isEmpty()) return null
            if (!text.all { it in '0'..'9' }) {
                throw IllegalArgumentException("Port could not be cast to integer value as '$text'")
            }
            val number = text.toIntOrNull()
            if (number == null || number > 65535) throw IllegalArgumentException("Port out of range 0-65535")
            return number
        }

    val username: String? get() = if (hasUserInfo) netloc.substringBeforeLast('@').substringBefore(':') else null
    val password: String?
        get() {
            if (!hasUserInfo) return null
            val info = netloc.substringBeforeLast('@')
            return if (info.contains(':')) info.substringAfter(':') else null
        }
}

/** Python `urlsplit`: scheme lower-cased; netloc only after `//`. */
private fun urlSplit(raw: String): Parts {
    var rest = raw
    var scheme = ""
    val m = Regex("^([A-Za-z][A-Za-z0-9+.-]*):").find(rest)
    if (m != null) {
        scheme = m.groupValues[1].lowercase()
        rest = rest.substring(m.value.length)
    }
    var netloc = ""
    if (rest.startsWith("//")) {
        val body = rest.substring(2)
        var end = body.length
        for (ch in "/?#") {
            val i = body.indexOf(ch)
            if (i in 0 until end) end = i
        }
        netloc = body.substring(0, end)
        rest = body.substring(end)
    }
    if (rest.contains('#')) rest = rest.substringBefore('#')
    var query = ""
    if (rest.contains('?')) {
        query = rest.substringAfter('?')
        rest = rest.substringBefore('?')
    }
    return Parts(scheme, netloc, rest, query)
}

private fun split(url: String): Parts {
    val raw = url.pyStrip()
    if (raw.isEmpty()) throw IllegalArgumentException("URL is empty")
    val parts = urlSplit(raw)
    if (parts.scheme != "http" && parts.scheme != "https") {
        throw IllegalArgumentException(
            "Unsupported URL scheme: ${parts.scheme.ifEmpty { "(none)" }}",
        )
    }
    if (parts.hostname == null) throw IllegalArgumentException("URL has no host: '$url'")
    return parts
}

private fun percentDecode(text: String): String {
    val s = text.replace('+', ' ')
    if (!s.contains('%')) return s
    val out = java.io.ByteArrayOutputStream()
    var i = 0
    val bytes = s.toByteArray(Charsets.UTF_8)
    while (i < bytes.size) {
        val b = bytes[i]
        if (b == '%'.code.toByte() && i + 2 < bytes.size) {
            val h = Character.digit(bytes[i + 1].toInt().toChar(), 16)
            val l = Character.digit(bytes[i + 2].toInt().toChar(), 16)
            if (h >= 0 && l >= 0) {
                out.write(h * 16 + l)
                i += 3
                continue
            }
        }
        out.write(b.toInt() and 0xff)
        i++
    }
    return String(out.toByteArray(), Charsets.UTF_8)
}

private fun quotePlus(text: String): String {
    val sb = StringBuilder()
    for (b in text.toByteArray(Charsets.UTF_8)) {
        val c = (b.toInt() and 0xff).toChar()
        when {
            c in 'A'..'Z' || c in 'a'..'z' || c in '0'..'9' || c == '_' || c == '.' || c == '-' || c == '~' -> sb.append(c)
            c == ' ' -> sb.append('+')
            else -> sb.append('%').append("%02X".format(b.toInt() and 0xff))
        }
    }
    return sb.toString()
}

/** Python `parse_qsl`. */
private fun parseQsl(query: String, keepBlank: Boolean): List<Pair<String, String>> {
    val result = ArrayList<Pair<String, String>>()
    for (field in query.split('&')) {
        if (field.isEmpty()) continue
        val eq = field.indexOf('=')
        val name: String
        val value: String
        if (eq < 0) {
            if (!keepBlank) continue
            name = field
            value = ""
        } else {
            name = field.substring(0, eq)
            value = field.substring(eq + 1)
            if (value.isEmpty() && !keepBlank) continue
        }
        result.add(percentDecode(name) to percentDecode(value))
    }
    return result
}

private fun urlEncode(pairs: List<Pair<String, String>>): String =
    pairs.joinToString("&") { (k, v) -> quotePlus(k) + "=" + quotePlus(v) }

private fun urlUnsplit(scheme: String, netloc: String, path: String, query: String): String {
    var url = path
    if (netloc.isNotEmpty()) {
        if (url.isNotEmpty() && !url.startsWith("/")) url = "/$url"
        url = "//$netloc$url"
    }
    if (scheme.isNotEmpty()) url = "$scheme:$url"
    if (query.isNotEmpty()) url += "?$query"
    return url
}

private fun isStartTime(value: String): Boolean {
    val v = value.pyStrip()
    if (v.isEmpty()) return false
    if (v.all { it in '0'..'9' }) return true
    return TIME_RE.matches(v) && v.any { it in '0'..'9' }
}

/** Lower-case [host] without a leading `www.` or `m.` (Python's `_bare_host`). */
private fun bareHost(host: String): String {
    var h = host.lowercase().trimEnd('.')
    for (prefix in listOf("www.", "m.")) {
        if (h.startsWith(prefix)) h = h.substring(prefix.length)
    }
    return h
}

/** "short", "full" for YouTube hosts, else null. */
private fun hostKind(host: String): String? {
    var h = bareHost(host)
    if (h.startsWith("music.")) h = h.substring("music.".length)
    if (h == SHORT_HOST) return "short"
    if (h in YOUTUBE_HOSTS) return "full"
    return null
}

/** "instagram", "tiktok" for those sites, else null. */
private fun siteKindOfHost(host: String): String? {
    val h = bareHost(host)
    if (h == INSTAGRAM_HOST) return "instagram"
    if (h in TIKTOK_HOSTS) return "tiktok"
    return null
}

private fun isAllDigits(text: String): Boolean = text.isNotEmpty() && text.all { it in '0'..'9' }

private fun videoIdOf(parts: Parts, kind: String): String? {
    val segments = parts.path.split('/').filter { it.isNotEmpty() }
    var candidate: String? = null
    if (kind == "short") {
        candidate = segments.firstOrNull()
    } else if (segments.isNotEmpty() && segments[0] in VIDEO_PATH_PREFIXES && segments.size > 1) {
        candidate = segments[1]
    } else if (segments.isNotEmpty() && segments[0] == "watch") {
        // dict(parse_qsl(query)).get("v"): the last duplicate wins.
        candidate = parseQsl(parts.query, false).lastOrNull { it.first == "v" }?.second
    }
    if (candidate != null && candidate.isNotEmpty() && VIDEO_ID_RE.matches(candidate)) return candidate
    return null
}

private fun startTimeOf(query: String): String? {
    for ((name, value) in parseQsl(query, true)) {
        if ((name == "t" || name == "start") && isStartTime(value)) return value.pyStrip()
    }
    return null
}

private fun canonicalVideo(videoId: String, query: String): String {
    val params = arrayListOf("v" to videoId)
    startTimeOf(query)?.let { params.add("t" to it) }
    return urlUnsplit("https", "www.youtube.com", "/watch", urlEncode(params))
}

private fun filterQuery(query: String, drop: Set<String>): String =
    urlEncode(
        parseQsl(query, true).filter { (name, _) -> name !in drop && !name.startsWith("utm_") },
    )

private fun normaliseYoutube(parts: Parts, kind: String): String {
    val videoId = videoIdOf(parts, kind)
    if (videoId != null) return canonicalVideo(videoId, parts.query)
    val segments = parts.path.split('/').filter { it.isNotEmpty() }
    if (segments.isNotEmpty() && segments[0] == "playlist") {
        val query = filterQuery(parts.query, TRACKING_PARAMS)
        return urlUnsplit("https", "www.youtube.com", "/playlist", query)
    }
    val path = parts.path.ifEmpty { "/" }
    return urlUnsplit("https", "www.youtube.com", path, filterQuery(parts.query, TRACKING_PARAMS))
}

/** Instagram/TikTok: lower-case host without `www.`/`m.`, share-link junk dropped. */
private fun normaliseSite(parts: Parts, site: String): String {
    val drop = if (site == "instagram") INSTAGRAM_DROP else TIKTOK_DROP
    val query = filterQuery(parts.query, drop)
    return urlUnsplit(parts.scheme.lowercase(), bareHost(parts.hostname ?: ""), parts.path, query)
}

private fun instagramKey(parts: Parts): String? {
    val segments = parts.path.split('/').filter { it.isNotEmpty() }
    if (segments.size >= 2 && segments[0] in INSTAGRAM_POST_PREFIXES) {
        val shortcode = segments[1]
        return if (VIDEO_ID_RE.matches(shortcode)) "instagram:$shortcode" else null
    }
    if (segments.size >= 3 && segments[0] == "stories" && segments[1] == "highlights") {
        // One highlight; the tray itself is classified elsewhere, unchanged.
        val highlightId = segments[2]
        return if (isAllDigits(highlightId)) "instagram:highlight:$highlightId" else null
    }
    if (segments.size >= 3 && segments[0] == "stories" && segments[1] != "highlights" &&
        isAllDigits(segments[2])
    ) {
        // One story; a story tray has no id and is queued item by item.
        return "instagram:story:${segments[1]}:${segments[2]}"
    }
    return null
}

private fun tiktokKey(parts: Parts, host: String): String? {
    val segments = parts.path.split('/').filter { it.isNotEmpty() }
    if (bareHost(host) in TIKTOK_SHORT_HOSTS) {
        // Short links are never resolved (no network): the code is the identity.
        val code = segments.firstOrNull()
        return if (code != null && VIDEO_ID_RE.matches(code)) "tiktok:short:$code" else null
    }
    if (segments.size >= 3 && segments[0].startsWith("@") && segments[1] == "video" &&
        isAllDigits(segments[2])
    ) {
        return "tiktok:${segments[2]}"
    }
    return null
}

/**
 * The canonical form of [url] used for queue dedupe.
 * @throws IllegalArgumentException for empty input or input without a host.
 */
fun normalizeUrl(url: String): String {
    val parts = split(url)
    val host = (parts.hostname ?: "").lowercase()
    val kind = hostKind(host)
    if (kind != null) return normaliseYoutube(parts, kind)
    val site = siteKindOfHost(host)
    if (site != null) return normaliseSite(parts, site)

    val scheme = parts.scheme
    var netloc = host
    val port = parts.port
    val isDefaultPort = (scheme == "http" && port == 80) || (scheme == "https" && port == 443)
    if (port != null && !isDefaultPort) netloc = "$host:$port"
    val user = parts.username
    if (user != null) {
        var userinfo: String = user
        val pw = parts.password
        if (pw != null) userinfo += ":$pw"
        netloc = "$userinfo@$netloc"
    }
    val query = filterQuery(parts.query, emptySet())
    return urlUnsplit(scheme, netloc, parts.path, query)
}

/** `"youtube:<ID>"`, `"instagram:..."`, `"tiktok:<id>"`, else null. */
fun videoKey(url: String): String? {
    val parts = split(url)
    val host = (parts.hostname ?: "").lowercase()
    val kind = hostKind(host)
    if (kind != null) {
        val videoId = videoIdOf(parts, kind) ?: return null
        return "youtube:$videoId"
    }
    return when (siteKindOfHost(host)) {
        "instagram" -> instagramKey(parts)
        "tiktok" -> tiktokKey(parts, host)
        else -> null
    }
}

/**
 * `"instagram"` / `"tiktok"` for a URL on those sites, else null.
 *
 * Never throws: an unparseable URL has no known site. Same host rules as
 * [normalizeUrl], so callers can pick wording per site.
 */
fun siteKind(url: String?): String? {
    if (url == null) return null
    val parts = try {
        split(url)
    } catch (_: IllegalArgumentException) {
        return null
    }
    return siteKindOfHost(parts.hostname ?: "")
}
