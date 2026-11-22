package com.desolate.elisium.media

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/*
 * Tolerant, read-only JSON helpers for the media parsers. Every accessor returns null
 * instead of throwing, so a missing or wrongly-typed field can never crash a parse.
 */

private val JSON = Json { ignoreUnknownKeys = true }

/** [text] as a JSON object, or null when it is blank, malformed, or not an object. */
internal fun parseJsonObject(text: String?): JsonObject? {
    if (text.isNullOrBlank()) return null
    return try {
        JSON.parseToJsonElement(text) as? JsonObject
    } catch (_: IllegalArgumentException) {
        // kotlinx.serialization's SerializationException is an IllegalArgumentException.
        null
    }
}

/** The member [name] of an object, or null. */
internal fun JsonElement?.field(name: String): JsonElement? = (this as? JsonObject)?.get(name)

/** The member [name] as an object, or null. */
internal fun JsonElement?.obj(name: String): JsonObject? = field(name) as? JsonObject

/** The member [name] as an array, or null. */
internal fun JsonElement?.arr(name: String): JsonArray? = field(name) as? JsonArray

/** The member [name] as a non-blank string, or null (numbers are accepted as text). */
internal fun JsonElement?.text(name: String): String? =
    (field(name) as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }

/** The member [name] as a whole number, or null. */
internal fun JsonElement?.number(name: String): Long? =
    (field(name) as? JsonPrimitive)?.contentOrNull?.trim()?.toLongOrNull()

/** The member [name] as a boolean, or null. */
internal fun JsonElement?.flag(name: String): Boolean? =
    (field(name) as? JsonPrimitive)?.contentOrNull?.trim()?.toBooleanStrictOrNull()

/** The first entry of the array member [name] as a whole number, or null. */
internal fun JsonElement?.firstNumber(name: String): Long? =
    arr(name)?.firstOrNull()?.let { (it as? JsonPrimitive)?.contentOrNull?.trim()?.toLongOrNull() }

/** The objects of an array, ignoring anything else in it. */
internal fun JsonArray.objects(): List<JsonObject> = filterIsInstance<JsonObject>()

/** The first object of an array, or null. */
internal fun JsonArray.firstObject(): JsonObject? = firstOrNull() as? JsonObject

private val KNOWN_EXTENSIONS = setOf(
    "jpg", "jpeg", "png", "webp", "heic", "mp4", "m4a", "mp3", "opus", "webm", "mov",
)

/**
 * The file extension a URL implies, lower-cased (`jpeg` becomes `jpg`), else [fallback].
 * Only the path is read, so signed query strings and fragments cannot confuse it.
 */
internal fun guessExt(url: String, fallback: String): String {
    val path = url.substringBefore('#').substringBefore('?')
    val name = path.substringAfterLast('/')
    val dot = name.lastIndexOf('.')
    if (dot < 0) return fallback
    val ext = name.substring(dot + 1).lowercase()
    if (ext !in KNOWN_EXTENSIONS) return fallback
    return if (ext == "jpeg") "jpg" else ext
}
