package com.desolate.elisium.media

import java.math.BigInteger

/**
 * Instagram shortcode <-> numeric media id. The shortcode is the media id written in the
 * base64 URL-safe alphabet (`A-Za-z0-9-_`), no padding, most significant digit first.
 *
 * BigInteger is used because a media id fills the whole unsigned 64-bit range, which does
 * not fit a signed Long once it passes 9,223,372,036,854,775,807.
 */
object ShortcodeId {
    private const val ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    private val BASE = BigInteger.valueOf(64)

    /** The numeric id for [shortcode], or null when it is empty or not base64-url. */
    fun toMediaId(shortcode: String): String? {
        if (shortcode.isEmpty()) return null
        var value = BigInteger.ZERO
        for (char in shortcode) {
            val digit = ALPHABET.indexOf(char)
            if (digit < 0) return null
            value = value.multiply(BASE).add(BigInteger.valueOf(digit.toLong()))
        }
        return value.toString()
    }

    /** The shortcode for a numeric [mediaId], or null when it is not a non-negative integer. */
    fun toShortcode(mediaId: String): String? {
        if (mediaId.isEmpty() || !mediaId.all { it in '0'..'9' }) return null
        var value = BigInteger(mediaId)
        if (value.signum() < 0) return null
        val digits = StringBuilder()
        do {
            val (quotient, remainder) = value.divideAndRemainder(BASE)
            digits.append(ALPHABET[remainder.toInt()])
            value = quotient
        } while (value.signum() > 0)
        return digits.reverse().toString()
    }
}
