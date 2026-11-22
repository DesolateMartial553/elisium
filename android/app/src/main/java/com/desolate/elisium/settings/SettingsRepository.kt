package com.desolate.elisium.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.desolate.elisium.media.PhotoMode
import com.desolate.elisium.media.SongLength
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

/** What the settings screen needs; [SettingsRepository] is the real one, tests use a fake. */
interface SettingsStore {
    val settings: Flow<Settings>
    suspend fun setConcurrency(value: Int): Boolean
    suspend fun setSpeedLimit(value: String?): Boolean
    suspend fun setPresetId(id: String)
    suspend fun setWifiOnly(value: Boolean)
    suspend fun setNotifyOnDone(value: Boolean)
    suspend fun setAppearance(value: Appearance)
    suspend fun setReduceMotion(value: Boolean)
    suspend fun setLastYtDlpCheck(value: Long)

    /** Photo-post settings (data layer for the 10E screens); the defaults make a store without them still work. */
    suspend fun setPhotoMode(value: PhotoMode) {}
    suspend fun setSongLength(value: SongLength) {}

    /** "Faster downloads" Auto / Off (data layer for the Downloads settings row). */
    suspend fun setFasterDownloads(value: FasterDownloads) {}
}

/**
 * Settings in a Preferences DataStore. Whatever is stored is validated on every read
 * ([validated]), so a hand-edited or old value falls back to its default. Compile-verified
 * only; the validation rules are JVM-tested in `SettingsRulesTest`.
 */
class SettingsRepository(context: Context) : SettingsStore {
    private val store = context.applicationContext.settingsStore

    override val settings: Flow<Settings> = store.data.map { it.toSettings() }

    suspend fun current(): Settings = settings.first()

    /** Stores [value] and returns true, or returns false (nothing stored) when it is outside 1-5. */
    override suspend fun setConcurrency(value: Int): Boolean {
        if (!isValidConcurrency(value)) return false
        store.edit { it[CONCURRENCY] = value }
        return true
    }

    /** Stores a valid limit (`2M`) or clears it for null/blank; returns false for an invalid string. */
    override suspend fun setSpeedLimit(value: String?): Boolean {
        val blank = value == null || value.isBlank()
        val valid = if (blank) null else validSpeedLimit(value) ?: return false
        store.edit { if (valid == null) it.remove(SPEED_LIMIT) else it[SPEED_LIMIT] = valid }
        return true
    }

    override suspend fun setPresetId(id: String) {
        store.edit { it[PRESET] = validPresetId(id) }
    }

    override suspend fun setWifiOnly(value: Boolean) {
        store.edit { it[WIFI_ONLY] = value }
    }

    override suspend fun setNotifyOnDone(value: Boolean) {
        store.edit { it[NOTIFY] = value }
    }

    override suspend fun setAppearance(value: Appearance) {
        store.edit { it[APPEARANCE] = value.storedValue }
    }

    override suspend fun setReduceMotion(value: Boolean) {
        store.edit { it[REDUCE_MOTION] = value }
    }

    /** Stores the last yt-dlp auto-update check time (default 0 = never checked). */
    override suspend fun setLastYtDlpCheck(value: Long) {
        store.edit { it[LAST_YTDLP_CHECK] = value.coerceAtLeast(0L) }
    }

    override suspend fun setPhotoMode(value: PhotoMode) {
        store.edit { it[PHOTO_MODE] = value.storedValue }
    }

    override suspend fun setSongLength(value: SongLength) {
        store.edit { it[SONG_LENGTH] = value.storedValue }
    }

    override suspend fun setFasterDownloads(value: FasterDownloads) {
        store.edit { it[FASTER_DOWNLOADS] = value.storedValue }
    }

    private fun Preferences.toSettings() = Settings(
        concurrency = this[CONCURRENCY] ?: Settings().concurrency,
        speedLimit = this[SPEED_LIMIT],
        presetId = this[PRESET] ?: Settings().presetId,
        wifiOnly = this[WIFI_ONLY] ?: Settings().wifiOnly,
        notifyOnDone = this[NOTIFY] ?: Settings().notifyOnDone,
        appearance = Appearance.fromStored(this[APPEARANCE]),
        reduceMotion = this[REDUCE_MOTION] ?: Settings().reduceMotion,
        lastYtDlpCheck = this[LAST_YTDLP_CHECK] ?: 0L,
        photoMode = PhotoMode.fromStored(this[PHOTO_MODE]),
        songLength = SongLength.fromStored(this[SONG_LENGTH]),
        fasterDownloads = FasterDownloads.fromStored(this[FASTER_DOWNLOADS]),
    ).validated()

    private companion object {
        val CONCURRENCY = intPreferencesKey("concurrency")
        val SPEED_LIMIT = stringPreferencesKey("speed_limit")
        val PRESET = stringPreferencesKey("preset_id")
        val WIFI_ONLY = booleanPreferencesKey("wifi_only")
        val NOTIFY = booleanPreferencesKey("notify_on_done")
        val APPEARANCE = stringPreferencesKey("appearance")
        val REDUCE_MOTION = booleanPreferencesKey("reduce_motion")
        val LAST_YTDLP_CHECK = longPreferencesKey("last_ytdlp_check")
        val PHOTO_MODE = stringPreferencesKey("photo_mode")
        val SONG_LENGTH = stringPreferencesKey("song_length")
        val FASTER_DOWNLOADS = stringPreferencesKey("faster_downloads")
    }
}
