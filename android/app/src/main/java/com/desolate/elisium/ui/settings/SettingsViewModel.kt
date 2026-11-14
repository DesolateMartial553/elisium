package com.desolate.elisium.ui.settings

import com.desolate.elisium.engine.MAX_CONCURRENCY
import com.desolate.elisium.engine.Preset
import com.desolate.elisium.engine.Presets
import com.desolate.elisium.settings.Appearance
import com.desolate.elisium.settings.CookiesCheck
import com.desolate.elisium.settings.CookiesStatus
import com.desolate.elisium.settings.CookiesStore
import com.desolate.elisium.settings.NoCookiesStore
import com.desolate.elisium.settings.SettingsStore
import com.desolate.elisium.settings.validSpeedLimit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Why the speed-limit field is not accepted. Mapped to a sentence in the UI (strings.xml). */
enum class SpeedLimitError { Invalid }

/** Blank means "no limit" and is fine; anything else must pass the engine's [validSpeedLimit] rule. */
fun speedLimitError(text: String): SpeedLimitError? =
    if (text.isBlank() || validSpeedLimit(text) != null) null else SpeedLimitError.Invalid

/** How long the speed-limit field must sit still before what was typed is stored. */
const val SPEED_LIMIT_DEBOUNCE_MS = 700L

/** The presets in display order, labels from [Presets]. */
fun presetChoices(): List<Preset> = Presets.PRESETS.values.toList()

data class SettingsUiState(
    val presetId: String = Presets.DEFAULT_ID,
    val concurrency: Int = 2,
    val speedLimitText: String = "",
    val speedLimitError: SpeedLimitError? = null,
    val wifiOnly: Boolean = true,
    val notifyOnDone: Boolean = true,
    val appearance: Appearance = Appearance.System,
    val reduceMotion: Boolean = false,
    /** Nothing imported, or how many cookies the imported cookies.txt holds. */
    val cookies: CookiesStatus = CookiesStatus.None,
    /** Why the last pick was not imported, or null when it was (or nothing was picked yet). */
    val cookiesRejected: CookiesCheck? = null,
) {
    val canDecrease: Boolean get() = concurrency > 1
    val canIncrease: Boolean get() = concurrency < MAX_CONCURRENCY
}

/**
 * Settings screen state. The speed-limit field keeps what the user typed (even if invalid) and only
 * stores values the engine accepts; a blank field clears the limit.
 */
class SettingsViewModel(
    private val store: SettingsStore,
    private val scope: CoroutineScope,
    private val speedLimitDebounceMs: Long = SPEED_LIMIT_DEBOUNCE_MS,
    private val cookies: CookiesStore = NoCookiesStore,
) {
    private val typed = MutableStateFlow<String?>(null)
    private val cookieStatus = MutableStateFlow(cookies.status())
    private val cookieRejected = MutableStateFlow<CookiesCheck?>(null)
    private var pendingSave: Job? = null

    val state: StateFlow<SettingsUiState> = combine(store.settings, typed, cookieStatus, cookieRejected) { s, text, jar, rejected ->
        val shown = text ?: (s.speedLimit ?: "")
        SettingsUiState(
            presetId = s.presetId,
            concurrency = s.concurrency,
            speedLimitText = shown,
            speedLimitError = speedLimitError(shown),
            wifiOnly = s.wifiOnly,
            notifyOnDone = s.notifyOnDone,
            appearance = s.appearance,
            reduceMotion = s.reduceMotion,
            cookies = jar,
            cookiesRejected = rejected,
        )
    }.stateIn(scope, SharingStarted.Eagerly, SettingsUiState(cookies = cookies.status()))

    fun setPreset(id: String) {
        scope.launch { store.setPresetId(id) }
    }

    fun increaseConcurrency() = stepConcurrency(+1)
    fun decreaseConcurrency() = stepConcurrency(-1)

    private fun stepConcurrency(delta: Int) {
        scope.launch {
            val current = store.settings.first().concurrency
            store.setConcurrency((current + delta).coerceIn(1, MAX_CONCURRENCY))
        }
    }

    /**
     * Every keystroke lands here. The text shows at once, but it is stored only after typing pauses
     * (or on [commitSpeedLimit]), so "10M" never runs a download at "1" byte/s on its way there.
     */
    fun setSpeedLimitText(text: String) {
        typed.value = text
        pendingSave?.cancel()
        pendingSave = scope.launch {
            delay(speedLimitDebounceMs)
            saveSpeedLimit(text)
        }
    }

    /** Stores the field now (focus lost, keyboard Done). */
    fun commitSpeedLimit() {
        val text = typed.value ?: return
        pendingSave?.cancel()
        pendingSave = scope.launch { saveSpeedLimit(text) }
    }

    private suspend fun saveSpeedLimit(text: String) {
        if (speedLimitError(text) == null) store.setSpeedLimit(text.ifBlank { null })
    }

    fun setWifiOnly(value: Boolean) {
        scope.launch { store.setWifiOnly(value) }
    }

    fun setNotifyOnDone(value: Boolean) {
        scope.launch { store.setNotifyOnDone(value) }
    }

    fun setAppearance(value: Appearance) {
        scope.launch { store.setAppearance(value) }
    }

    fun setReduceMotion(value: Boolean) {
        scope.launch { store.setReduceMotion(value) }
    }

    /**
     * Stores a picked cookies.txt (the caller reads the file off the main thread). A file that is
     * not a cookie file is not stored, and [SettingsUiState.cookiesRejected] explains why.
     */
    fun importCookies(text: String?) {
        val result = cookies.import(text)
        cookieStatus.value = result.status
        cookieRejected.value = result.check.takeIf { it !is CookiesCheck.Valid }
    }

    /** Deletes the imported cookies.txt; nothing else is touched. */
    fun removeCookies() {
        cookieStatus.value = cookies.remove()
        cookieRejected.value = null
    }
}
