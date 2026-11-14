package com.desolate.elisium.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

/**
 * Settings in a Preferences DataStore. Whatever is stored is validated on every read
 * ([validated]), so a hand-edited or old value falls back to its default. Compile-verified
 * only; the validation rules are JVM-tested in `SettingsRulesTest`.
 */
class SettingsRepository(context: Context) {
    private val store = context.applicationContext.settingsStore

    val settings: Flow<Settings> = store.data.map { it.toSettings() }

    suspend fun current(): Settings = settings.first()

    /** Stores [value] and returns true, or returns false (nothing stored) when it is outside 1-5. */
    suspend fun setConcurrency(value: Int): Boolean {
        if (!isValidConcurrency(value)) return false
        store.edit { it[CONCURRENCY] = value }
        return true
    }

    /** Stores a valid limit (`2M`) or clears it for null/blank; returns false for an invalid string. */
    suspend fun setSpeedLimit(value: String?): Boolean {
        val blank = value == null || value.isBlank()
        val valid = if (blank) null else validSpeedLimit(value) ?: return false
        store.edit { if (valid == null) it.remove(SPEED_LIMIT) else it[SPEED_LIMIT] = valid }
        return true
    }

    suspend fun setPresetId(id: String) = store.edit { it[PRESET] = validPresetId(id) }

    suspend fun setWifiOnly(value: Boolean) = store.edit { it[WIFI_ONLY] = value }

    suspend fun setNotifyOnDone(value: Boolean) = store.edit { it[NOTIFY] = value }

    private fun Preferences.toSettings() = Settings(
        concurrency = this[CONCURRENCY] ?: Settings().concurrency,
        speedLimit = this[SPEED_LIMIT],
        presetId = this[PRESET] ?: Settings().presetId,
        wifiOnly = this[WIFI_ONLY] ?: Settings().wifiOnly,
        notifyOnDone = this[NOTIFY] ?: Settings().notifyOnDone,
    ).validated()

    private companion object {
        val CONCURRENCY = intPreferencesKey("concurrency")
        val SPEED_LIMIT = stringPreferencesKey("speed_limit")
        val PRESET = stringPreferencesKey("preset_id")
        val WIFI_ONLY = booleanPreferencesKey("wifi_only")
        val NOTIFY = booleanPreferencesKey("notify_on_done")
    }
}
