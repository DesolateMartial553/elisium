package com.desolate.elisium.ui.history

import com.desolate.elisium.engine.HistoryStore
import com.desolate.elisium.engine.OutputStore
import java.time.LocalDate
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

const val HISTORY_PAGE = 100
const val SEARCH_DEBOUNCE_MS = 250L

/**
 * History list with a debounced search. Every database and file-existence call runs on [io]
 * (Room blocks, MediaStore queries block). [requeue] puts a link back in the download queue and
 * returns the confirmation line.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HistoryViewModel(
    private val history: HistoryStore,
    private val output: OutputStore,
    private val requeue: suspend (String) -> String,
    private val scope: CoroutineScope,
    private val io: CoroutineDispatcher,
    private val zone: ZoneId = ZoneId.systemDefault(),
    private val locale: Locale = Locale.getDefault(),
    private val today: () -> LocalDate = { LocalDate.now(zone) },
) {
    private val _query = MutableStateFlow("")
    val query: StateFlow<String> = _query

    private val reloads = MutableStateFlow(0)

    /** Rows for the current search; blank search shows the most recent entries. */
    val rows: StateFlow<List<HistoryRowModel>> = combine(_query, reloads) { q, _ -> q }
        .mapLatest { q ->
            // Typing restarts this block (mapLatest), so only a pause in typing reaches the database.
            if (q.isNotBlank()) delay(SEARCH_DEBOUNCE_MS)
            load(q)
        }
        .flowOn(io)
        .stateIn(scope, SharingStarted.Eagerly, emptyList())

    private val _site = MutableStateFlow<String?>(null)

    /** The selected site chip (null = All). */
    val site: StateFlow<String?> = _site

    /** "All" is implied; these are the sites in the current rows (the selected one stays even if a search hides it). */
    val sites: StateFlow<List<String>> = combine(rows, _site) { list, selected ->
        val found = siteOptions(list)
        if (selected != null && selected !in found) found + selected else found
    }.stateIn(scope, SharingStarted.Eagerly, emptyList())

    /** The rows for the current search and site filter, grouped by day. */
    val groups: StateFlow<List<DayGroup>> = combine(rows, _site) { list, selected ->
        groupByDay(filterBySite(list, selected), today(), locale)
    }.stateIn(scope, SharingStarted.Eagerly, emptyList())

    fun setSite(site: String?) {
        _site.value = site
    }

    private val messageChannel = Channel<String>(Channel.BUFFERED)
    val messages: Flow<String> = messageChannel.receiveAsFlow()

    private fun load(q: String): List<HistoryRowModel> {
        val text = q.trim()
        val records = if (text.isEmpty()) history.recent(HISTORY_PAGE) else history.search(text, HISTORY_PAGE)
        return records.map { it.toRowModel(output::existsAt, zone, locale) }
    }

    fun setQuery(text: String) {
        _query.value = text
    }

    /** Re-reads the list (screen shown again, a download finished). */
    fun reload() {
        reloads.value += 1
    }

    /** Removes the entry only; the downloaded file stays where it is. */
    fun deleteFromHistory(id: Long) {
        scope.launch {
            withContext(io) { history.delete(id) }
            reload()
        }
    }

    fun downloadAgain(url: String) {
        scope.launch { messageChannel.trySend(requeue(url)) }
    }
}
