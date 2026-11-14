package com.desolate.elisium.ui.settings

import com.desolate.elisium.engine.MAX_CONCURRENCY
import com.desolate.elisium.engine.Preset
import com.desolate.elisium.engine.Presets
import com.desolate.elisium.settings.Appearance
import com.desolate.elisium.settings.SettingsStore
import com.desolate.elisium.settings.validSpeedLimit
import kotlinx.coroutines.CoroutineScope
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
) {
    val canDecrease: Boolean get() = concurrency > 1
    val canIncrease: Boolean get() = concurrency < MAX_CONCURRENCY
}

/**
 * Settings screen state. The speed-limit field keeps what the user typed (even if invalid) and only
 * stores values the engine accepts; a blank field clears the limit.
 */
class SettingsViewModel(private val store: SettingsStore, private val scope: CoroutineScope) {
    private val typed = MutableStateFlow<String?>(null)

    val state: StateFlow<SettingsUiState> = combine(store.settings, typed) { s, text ->
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
        )
    }.stateIn(scope, SharingStarted.Eagerly, SettingsUiState())

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

    fun setSpeedLimitText(text: String) {
        typed.value = text
        if (speedLimitError(text) == null) {
            scope.launch { store.setSpeedLimit(text.ifBlank { null }) }
        }
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
}
