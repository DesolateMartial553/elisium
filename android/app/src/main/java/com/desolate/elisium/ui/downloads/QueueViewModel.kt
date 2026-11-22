package com.desolate.elisium.ui.downloads

import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.engine.TERMINAL_STATES
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.service.extractUrls
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** What the Downloads screen needs from the app; the real one wraps the queue and coordinator. */
interface QueueGateway {
    val items: Flow<List<QueueItem>>
    val holdReason: Flow<String?>
    val serviceError: Flow<String?>

    /** Queues [urls] with the saved settings and returns the confirmation line. Off the main thread. */
    suspend fun addLinks(urls: List<String>): String
    fun pause(id: Int)
    fun resume(id: Int)
    fun retry(id: Int)
    fun cancel(id: Int)
    fun pauseAll()
    fun cancelAll()
}

/** What the confirm dialog is asking about. */
sealed interface CancelPrompt {
    data class One(val id: Int, val title: String) : CancelPrompt
    data object All : CancelPrompt
}

/**
 * State and actions of the Downloads screen. Plain class (no Android types) so a JVM test can
 * drive it with a fake [QueueGateway]; [ElisiumViewModel] owns the real instance.
 */
class QueueViewModel(
    private val gateway: QueueGateway,
    private val scope: CoroutineScope,
    stateLabel: (String) -> String = { it },
    percentLabel: (Int) -> String = { "$it percent" },
) {
    val rows: StateFlow<List<QueueRowModel>> = combine(gateway.items, gateway.holdReason) { list, hold ->
        val waitingForWifi = hold == WAITING_FOR_WIFI
        list.map { it.toRowModel(waitingForWifi) }
    }
        .stateIn(scope, SharingStarted.Eagerly, emptyList())

    private val _filter = MutableStateFlow(QueueFilter.All)

    /** The selected chip. */
    val filter: StateFlow<QueueFilter> = _filter.asStateFlow()

    fun setFilter(value: QueueFilter) {
        _filter.value = value
    }

    /** Count per chip (zero stays 0). */
    val counts: StateFlow<Map<QueueFilter, Int>> = rows
        .map { filterCounts(it) }
        .stateIn(scope, SharingStarted.Eagerly, filterCounts(emptyList()))

    /** The rows under the selected chip, in queue order. */
    val visibleRows: StateFlow<List<QueueRowModel>> = combine(rows, _filter) { list, f -> applyFilter(list, f) }
        .stateIn(scope, SharingStarted.Eagerly, emptyList())

    val banner: StateFlow<Banner?> = combine(gateway.holdReason, gateway.serviceError, ::bannerFor)
        .stateIn(scope, SharingStarted.Eagerly, null)

    /** True while "Pause all" / "Cancel all" would do something. */
    val hasUnfinished: StateFlow<Boolean> = rows
        .map { list -> list.any { it.state !in TERMINAL_STATES } }
        .stateIn(scope, SharingStarted.Eagerly, false)

    private val _announcement = MutableStateFlow("")

    /** Latest thing worth reading aloud (state changes, 25% steps); shown in a polite live region. */
    val announcement: StateFlow<String> = _announcement.asStateFlow()

    private val announcer = ProgressAnnouncer(stateLabel, percentLabel)

    private val _prompt = MutableStateFlow<CancelPrompt?>(null)
    val cancelPrompt: StateFlow<CancelPrompt?> = _prompt.asStateFlow()

    private val messageChannel = Channel<String>(Channel.BUFFERED)

    /** One-shot lines for the Snackbar (buffered until the screen collects them). */
    val messages: Flow<String> = messageChannel.receiveAsFlow()

    private val _linksAdded = MutableSharedFlow<Int>(extraBufferCapacity = 8)

    /** Emits the number of links queued after every successful add (drives the permission prompt). */
    val linksAdded: SharedFlow<Int> = _linksAdded

    init {
        scope.launch {
            rows.collect { list ->
                val said = announcer.update(list)
                if (said.isNotEmpty()) _announcement.value = said.joinToString(" ")
            }
        }
    }

    /**
     * Queues every link found in [text]. Returns true when at least one link was found, so the
     * input field can clear itself; with none, a Snackbar line says so and the text stays.
     */
    fun addFromText(text: String?): Boolean {
        val urls = extractUrls(text)
        scope.launch {
            val line = gateway.addLinks(urls)
            messageChannel.trySend(line)
            if (urls.isNotEmpty()) _linksAdded.emit(urls.size)
        }
        return urls.isNotEmpty()
    }

    fun pause(id: Int) { gateway.pause(id) }
    fun resume(id: Int) { gateway.resume(id) }
    fun retry(id: Int) { gateway.retry(id) }

    /** Cancels at once for a waiting item; a running one raises the confirm dialog first. */
    fun requestCancel(id: Int) {
        val row = rows.value.firstOrNull { it.id == id } ?: return
        if (needsCancelConfirmation(row.state)) _prompt.value = CancelPrompt.One(id, row.title) else gateway.cancel(id)
    }

    fun requestCancelAll() {
        if (hasUnfinished.value) _prompt.value = CancelPrompt.All
    }

    fun confirmCancel() {
        when (val p = _prompt.value) {
            is CancelPrompt.One -> gateway.cancel(p.id)
            CancelPrompt.All -> gateway.cancelAll()
            null -> Unit
        }
        _prompt.value = null
    }

    fun dismissCancel() {
        _prompt.value = null
    }

    fun pauseAll() = gateway.pauseAll()
}
