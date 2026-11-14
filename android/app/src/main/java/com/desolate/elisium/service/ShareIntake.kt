package com.desolate.elisium.service

private val URL_RE = Regex("https?://[^\\s<>\"']+", RegexOption.IGNORE_CASE)
private const val TRAILING = ".,;:!?'\""

/**
 * Every http/https URL in free text (a share sheet's `EXTRA_TEXT` is often "Title - https://...").
 * Trailing punctuation is dropped (a closing bracket only when it has no opener inside the URL),
 * duplicates are removed, order is kept.
 */
fun extractUrls(text: String?): List<String> {
    if (text.isNullOrBlank()) return emptyList()
    val found = LinkedHashSet<String>()
    for (match in URL_RE.findAll(text)) {
        var url = match.value
        while (url.isNotEmpty()) {
            val last = url.last()
            val drop = when {
                last in TRAILING -> true
                last == ')' -> url.count { it == '(' } < url.count { it == ')' }
                last == ']' -> url.count { it == '[' } < url.count { it == ']' }
                last == '}' -> url.count { it == '{' } < url.count { it == '}' }
                else -> false
            }
            if (!drop) break
            url = url.dropLast(1)
        }
        // "https://" with nothing after it is not a link.
        if (url.substringAfter("://", "").isNotEmpty()) found.add(url)
    }
    return found.toList()
}

/** The one-line confirmation shown after a share: "Added 1 link", "Added 2 links (1 already in the list)". */
fun shareConfirmation(added: Int, alreadyQueued: Int, found: Int, retried: Int = 0): String {
    if (found == 0) return "No links found in the shared text"
    val links = if (added == 1) "link" else "links"
    val head = when {
        retried == 0 -> "Added $added $links"
        added == 0 -> "$retried ${if (retried == 1) "link" else "links"} queued again"
        else -> "Added $added $links, $retried queued again"
    }
    return if (alreadyQueued > 0) "$head ($alreadyQueued already in the list)" else head
}
