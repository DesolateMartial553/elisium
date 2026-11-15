package com.desolate.elisium.ui.settings

import com.desolate.elisium.backend.UpdateResult
import com.desolate.elisium.backend.YtDlpUpdateService
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
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOf
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

/** What the yt-dlp update line shows. */
sealed interface UpdateUi {
    data object Idle : UpdateUi
    data object Running : UpdateUi
    data class Updated(val version: String) : UpdateUi
    data class UpToDate(val version: String) : UpdateUi
    data class Failed(val reason: String) : UpdateUi
}

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
    val update: UpdateUi = UpdateUi.Idle,
    /** A download is running or waiting: the yt-dlp update button is disabled meanwhile. */
    val downloadsActive: Boolean = false,
) {
    /** The "Update yt-dlp" button is allowed unless an update runs or a download is active. */
    val canUpdate: Boolean get() = update != UpdateUi.Running && !downloadsActive

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
    private val updates: YtDlpUpdateService? = null,
    downloadsActive: Flow<Boolean> = flowOf(false),
) {
    private val lastUpdate = MutableStateFlow<UpdateUi>(UpdateUi.Idle)
    private val updateUi: Flow<Pair<UpdateUi, Boolean>> =
        combine(lastUpdate, updates?.running ?: flowOf(false), downloadsActive) { last, running, active ->
            (if (running) UpdateUi.Running else last) to active
        }

    private val typed = MutableStateFlow<String?>(null)
    private val cookieStatus = MutableStateFlow(cookies.status())
    private val cookieRejected = MutableStateFlow<CookiesCheck?>(null)
    private var pendingSave: Job? = null

    val state: StateFlow<SettingsUiState> = combine(store.settings, typed, cookieStatus, cookieRejected, updateUi) { s, text, jar, rejected, upd ->
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
            update = upd.first,
            downloadsActive = upd.second,
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
     * Stores a picked cookies.txt or a captured Instagram session (the caller reads the file off the
     * main thread). A file that is not a cookie file is not stored, and [SettingsUiState.cookiesRejected]
     * explains why. Returns true when it was stored.
     */
    fun importCookies(text: String?): Boolean {
        val result = cookies.import(text)
        cookieStatus.value = result.status
        cookieRejected.value = result.check.takeIf { it !is CookiesCheck.Valid }
        // A rejected text keeps whatever was stored before, so the answer is about this text, not the status.
        return result.check is CookiesCheck.Valid && result.status is CookiesStatus.Imported
    }

    /** The "Update yt-dlp" button: ignored while an update runs or a download is active. */
    fun updateYtDlp() {
        val service = updates ?: return
        if (!state.value.canUpdate) return
        scope.launch {
            val result = service.run() ?: return@launch // another update is already running
            lastUpdate.value = when (result) {
                is UpdateResult.Updated -> UpdateUi.Updated(result.version)
                is UpdateResult.AlreadyUpToDate -> UpdateUi.UpToDate(result.version)
                is UpdateResult.Failed -> UpdateUi.Failed(result.reason)
            }
        }
    }

    /** Deletes the imported cookies.txt; nothing else is touched. */
    fun removeCookies() {
        cookieStatus.value = cookies.remove()
        cookieRejected.value = null
    }
}
