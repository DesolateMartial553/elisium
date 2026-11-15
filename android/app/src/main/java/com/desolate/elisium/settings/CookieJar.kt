package com.desolate.elisium.settings

import android.content.Context
import java.io.File

/** What an import attempt found, and what Settings now shows. */
data class CookiesImport(val check: CookiesCheck, val status: CookiesStatus)

/**
 * The cookies file, as Settings sees it. The in-app Instagram sign-in writes it (a WebView session);
 * a `cookies.txt` picked with the system document picker is still accepted as the advanced route.
 * Only its path is ever given to yt-dlp.
 */
interface CookiesStore {
    fun status(): CookiesStatus

    /** Validates [text] and stores it when it is a cookie file; nothing is stored otherwise. */
    fun import(text: String?): CookiesImport

    fun remove(): CookiesStatus

    /** The stored file, or null when nothing is imported. */
    fun file(): File?
}

/** Reports "nothing imported" and stores nothing (used by previews and simple tests). */
object NoCookiesStore : CookiesStore {
    override fun status(): CookiesStatus = CookiesStatus.None
    override fun import(text: String?): CookiesImport = CookiesImport(checkCookiesFile(text), CookiesStatus.None)
    override fun remove(): CookiesStatus = CookiesStatus.None
    override fun file(): File? = null
}

/**
 * [CookiesStore] over app-private storage (`filesDir/cookies/cookies.txt`). Compile-verified only:
 * the validation rules are JVM-tested in `CookiesFileTest`. The contents are never logged.
 */
class CookieJar(context: Context) : CookiesStore {
    val file: File = File(File(context.applicationContext.filesDir, "cookies"), "cookies.txt")

    override fun file(): File? = file.takeIf { it.isFile }

    override fun status(): CookiesStatus {
        val text = try {
            if (file.isFile) file.readText() else return CookiesStatus.None
        } catch (_: Exception) {
            return CookiesStatus.None
        }
        return when (val check = checkCookiesFile(text)) {
            is CookiesCheck.Valid -> CookiesStatus.Imported(check.count)
            CookiesCheck.Empty, CookiesCheck.WrongFormat -> CookiesStatus.None
        }
    }

    override fun import(text: String?): CookiesImport {
        val check = checkCookiesFile(text)
        if (check !is CookiesCheck.Valid || text == null) return CookiesImport(check, status())
        val saved = try {
            file.parentFile?.mkdirs()
            file.writeText(text.removePrefix("\uFEFF"))
            true
        } catch (_: Exception) {
            false
        }
        return CookiesImport(check, if (saved) CookiesStatus.Imported(check.count) else status())
    }

    override fun remove(): CookiesStatus {
        try {
            file.delete()
            file.parentFile?.delete() // only succeeds when empty
        } catch (_: Exception) {
        }
        return CookiesStatus.None
    }
}
