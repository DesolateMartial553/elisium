package com.desolate.elisium.media

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** A finished HTTP call: the status and the body text (empty for a download). */
data class HttpResult(val code: Int, val body: String)

/** The only network seam of the media engine; tests give a fake, a device gets [UrlConnectionTransport]. */
interface HttpTransport {
    /** GET [url] and read the body as text. IO failures throw [IOException]. */
    @Throws(IOException::class)
    fun get(url: String, headers: Map<String, String>, token: CancelToken): HttpResult

    /** GET [url] into [part], resuming from its current length with a Range header. Returns the HTTP status. */
    @Throws(IOException::class)
    fun download(url: String, headers: Map<String, String>, part: File, token: CancelToken): Int
}

private const val CONNECT_TIMEOUT_MS = 15_000
private const val READ_TIMEOUT_MS = 20_000
private const val MAX_BODY_BYTES = 8 * 1024 * 1024

/** [HttpTransport] over `HttpURLConnection` (no new dependency). Compile-verified; the logic around it is JVM-tested. */
class UrlConnectionTransport : HttpTransport {
    private fun open(url: String, headers: Map<String, String>, token: CancelToken): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = CONNECT_TIMEOUT_MS
        conn.readTimeout = READ_TIMEOUT_MS
        conn.instanceFollowRedirects = true
        headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }
        token.onCancel { conn.disconnect() }
        return conn
    }

    override fun get(url: String, headers: Map<String, String>, token: CancelToken): HttpResult {
        val conn = open(url, headers, token)
        try {
            val code = try {
                conn.responseCode
            } catch (e: IOException) {
                // Android's HttpURLConnection throws this (instead of returning 401) when a 401 carries no
                // WWW-Authenticate header, which is exactly what Instagram sends to a signed-out client.
                if (e.message?.contains("No authentication challenges found", ignoreCase = true) == true) {
                    return HttpResult(401, "")
                }
                throw e
            }
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.use { input ->
                val out = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(16 * 1024)
                while (out.size() < MAX_BODY_BYTES) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    out.write(buffer, 0, n)
                }
                out.toString(Charsets.UTF_8.name())
            }.orEmpty()
            return HttpResult(code, body)
        } finally {
            conn.disconnect()
        }
    }

    override fun download(url: String, headers: Map<String, String>, part: File, token: CancelToken): Int {
        val have = if (part.isFile) part.length() else 0L
        val sent = if (have > 0) headers + ("Range" to "bytes=$have-") else headers
        val conn = open(url, sent, token)
        try {
            val code = conn.responseCode
            if (code !in 200..299) return code
            val append = code == 206 && have > 0
            part.parentFile?.mkdirs()
            FileOutputStream(part, append).use { out ->
                conn.inputStream.use { input ->
                    val buffer = ByteArray(32 * 1024)
                    while (!token.cancelled) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        out.write(buffer, 0, n)
                    }
                }
            }
            return code
        } finally {
            conn.disconnect()
        }
    }
}

/** A browser-like User-Agent; Instagram and TikTok both answer a plain client with a wall. */
const val BROWSER_USER_AGENT =
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"

/** One cookie of a Netscape `cookies.txt`. Never printed or logged. */
internal class CookieEntry(val domain: String, val name: String, val value: String)

/** The cookies of [text] (a Netscape file) that apply to [host]. `#HttpOnly_` rows count; comments do not. */
internal fun cookiesForHost(text: String, host: String): List<CookieEntry> {
    val wanted = host.lowercase()
    val out = ArrayList<CookieEntry>()
    for (raw in text.lineSequence()) {
        var line = raw.trimEnd('\r')
        if (line.startsWith("#HttpOnly_")) line = line.removePrefix("#HttpOnly_")
        if (line.isBlank() || line.startsWith("#")) continue
        val fields = line.split('\t')
        if (fields.size != 7) continue
        val domain = fields[0].trim().lowercase().trimStart('.')
        if (domain.isEmpty() || !(wanted == domain || wanted.endsWith(".$domain"))) continue
        val name = fields[5].trim()
        if (name.isEmpty()) continue
        out.add(CookieEntry(domain, name, fields[6]))
    }
    return out
}

/** The `Cookie:` header value for [host], or null when the file has no cookie for it. */
internal fun cookieHeader(file: File?, host: String): String? {
    if (file == null || !file.isFile) return null
    val text = try {
        file.readText()
    } catch (_: Exception) {
        return null
    }
    val cookies = cookiesForHost(text, host)
    if (cookies.isEmpty()) return null
    return cookies.joinToString("; ") { "${it.name}=${it.value}" }
}

/** The value of cookie [name] for [host], or null. */
internal fun cookieValue(file: File?, host: String, name: String): String? {
    if (file == null || !file.isFile) return null
    val text = try {
        file.readText()
    } catch (_: Exception) {
        return null
    }
    return cookiesForHost(text, host).lastOrNull { it.name == name }?.value
}
