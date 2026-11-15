package com.desolate.elisium.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.CreationExtras
import com.desolate.elisium.ElisiumApp
import com.desolate.elisium.R
import com.desolate.elisium.engine.ACTIVE_STATES
import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.ui.downloads.QueueGateway
import com.desolate.elisium.ui.downloads.QueueViewModel
import com.desolate.elisium.ui.history.HistoryViewModel
import com.desolate.elisium.ui.settings.SettingsViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** [QueueGateway] over the application's coordinator; empty until the engine is ready. */
@OptIn(ExperimentalCoroutinesApi::class)
class AppQueueGateway(private val app: ElisiumApp) : QueueGateway {
    override val items: Flow<List<QueueItem>> =
        app.coordinator.flatMapLatest { it?.queue?.items ?: flowOf(emptyList()) }
    override val holdReason: Flow<String?> = app.coordinator.flatMapLatest { it?.holdReason ?: flowOf(null) }
    override val serviceError: Flow<String?> = app.coordinator.flatMapLatest { it?.serviceError ?: flowOf(null) }

    // Room refuses main-thread access and queue actions write history, so everything runs on the app's IO scope.
    override suspend fun addLinks(urls: List<String>): String = withContext(Dispatchers.IO) { app.addLinks(urls) }
    override fun pause(id: Int) { app.scope.launch { app.queue?.pause(id) } }
    override fun resume(id: Int) { app.scope.launch { app.queue?.resume(id) } }
    override fun retry(id: Int) { app.scope.launch { app.queue?.retry(id) } }
    override fun cancel(id: Int) { app.scope.launch { app.queue?.cancel(id) } }
    override fun pauseAll() { app.scope.launch { app.coordinator.value?.pauseAll() } }
    override fun cancelAll() { app.scope.launch { app.coordinator.value?.cancelAll() } }
}

/** Holds the three screen models for the lifetime of the activity (survives rotation). Compile-verified only. */
class ElisiumViewModel(val app: ElisiumApp) : ViewModel() {
    val queue = QueueViewModel(
        gateway = AppQueueGateway(app),
        scope = viewModelScope,
        stateLabel = { app.getString(stateLabelRes(it)) },
        percentLabel = { app.getString(R.string.percent_spoken, it) },
    )
    val history = HistoryViewModel(
        history = app.history,
        output = app.outputStore,
        requeue = { url -> app.addLinks(listOf(url)) },
        scope = viewModelScope,
        io = Dispatchers.IO,
    )
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    private val downloadsActive: Flow<Boolean> = app.coordinator.flatMapLatest { c ->
        c?.queue?.items?.map { items -> items.any { it.state in ACTIVE_STATES || it.state == "queued" } } ?: flowOf(false)
    }
    val settings = SettingsViewModel(
        app.settingsRepository,
        viewModelScope,
        cookies = app.cookieJar,
        updates = app.ytDlpUpdates,
        downloadsActive = downloadsActive,
    )

    private val extraMessages = kotlinx.coroutines.channels.Channel<String>(kotlinx.coroutines.channels.Channel.BUFFERED)

    /** One-off lines from screens (e.g. "No app can open this file") for the shell's Snackbar. */
    val screenMessages: Flow<String> = extraMessages.receiveAsFlow()
    fun postMessage(line: String) { extraMessages.trySend(line) }

    class Factory(private val app: ElisiumApp) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>, extras: CreationExtras): T = ElisiumViewModel(app) as T
    }
}
