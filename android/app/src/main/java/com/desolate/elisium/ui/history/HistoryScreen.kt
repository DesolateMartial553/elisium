package com.desolate.elisium.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.components.ElisiumCard
import com.desolate.elisium.ui.components.ElisiumTextButton
import com.desolate.elisium.ui.components.ElisiumTextField
import com.desolate.elisium.ui.components.EmptyState
import com.desolate.elisium.ui.components.FilterChip
import com.desolate.elisium.ui.components.ShelfPreviews
import com.desolate.elisium.ui.components.Thumbnail
import com.desolate.elisium.ui.components.enterRise
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.NumericStyle
import com.desolate.elisium.ui.theme.Sizes

/** The tone of a history state's word: done green, failed red, everything else quiet. Never colour alone: the word is always shown. */
fun historyTone(state: String): com.desolate.elisium.ui.downloads.Tone = when (state) {
    "done" -> com.desolate.elisium.ui.downloads.Tone.Positive
    "failed" -> com.desolate.elisium.ui.downloads.Tone.Negative
    else -> com.desolate.elisium.ui.downloads.Tone.Faint
}

@Composable
fun HistoryScreen(vm: HistoryViewModel, showMessage: (String) -> Unit, modifier: Modifier = Modifier) {
    val rows by vm.rows.collectAsStateWithLifecycle()
    val groups by vm.groups.collectAsStateWithLifecycle()
    val sites by vm.sites.collectAsStateWithLifecycle()
    val site by vm.site.collectAsStateWithLifecycle()
    val query by vm.query.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val noApp = stringResource(R.string.history_no_app)
    val noFolder = stringResource(R.string.folder_no_app)
    val shareTitle = stringResource(R.string.history_share_chooser)
    val reduced = ElisiumTheme.extras.reducedMotion
    val seen = remember { HashSet<Long>() }
    val gutter = Sizes.GUTTER_PHONE.dp

    LaunchedEffect(Unit) { vm.reload() }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 16.dp),
        verticalArrangement = Arrangement.spacedBy(Sizes.GAP.dp),
    ) {
        item(key = "search") {
            ElisiumTextField(
                value = query,
                onValueChange = vm::setQuery,
                label = stringResource(R.string.history_search_label),
                placeholder = stringResource(R.string.history_search_label),
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                modifier = Modifier.padding(horizontal = gutter),
            )
        }
        if (sites.isNotEmpty()) {
            item(key = "sites") {
                LazyRow(contentPadding = PaddingValues(horizontal = gutter), horizontalArrangement = Arrangement.spacedBy(Sizes.GAP.dp)) {
                    item(key = "all") {
                        val all = stringResource(R.string.history_site_all)
                        FilterChip(all, null, site == null, { vm.setSite(null) }, stringResource(R.string.history_site_filter, all))
                    }
                    items(sites, key = { it }) { name ->
                        FilterChip(name, null, site == name, { vm.setSite(name) }, stringResource(R.string.history_site_filter, name))
                    }
                }
            }
        }
        if (groups.isEmpty()) {
            item(key = "empty") {
                EmptyState(
                    stringResource(if (query.isBlank() && site == null && rows.isEmpty()) R.string.history_empty else R.string.history_no_matches),
                )
            }
        }
        for (group in groups) {
            item(key = "day-${group.heading}") {
                Text(
                    group.heading,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = gutter, vertical = 4.dp).semantics { heading() },
                )
            }
            items(group.rows, key = { it.id }) { row ->
                val firstTime = seen.add(row.id)
                HistoryRow(
                    modifier = (if (reduced) Modifier else Modifier.animateItem()).enterRise(firstTime).padding(horizontal = gutter),
                    row = row,
                    onOpen = { row.filePath?.let { if (!openFinished(context, it, row.multiFile)) showMessage(if (row.multiFile) noFolder else noApp) } },
                    onShowInFolder = { row.filePath?.let { if (!openFolder(context, it)) showMessage(noFolder) } },
                    onShare = { shareLink(context, row.url, shareTitle) },
                    onAgain = { vm.downloadAgain(row.url) },
                    onDelete = { vm.deleteFromHistory(row.id) },
                )
            }
        }
    }
}

/**
 * One finished or failed download: a small thumbnail block, the title, "Site - date time", the state word in its tone,
 * the note, then "Open / Show in folder / Download again" (plus Share link and Remove).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HistoryRow(
    row: HistoryRowModel,
    onOpen: () -> Unit,
    onShowInFolder: () -> Unit,
    onShare: () -> Unit,
    onAgain: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val missing = stringResource(R.string.history_file_missing)
    val extras = ElisiumTheme.extras
    val spoken = listOfNotNull(
        row.title, row.site, stateWord, row.date.ifEmpty { null }, row.note,
        if (row.fileStatus == FileStatus.Missing) missing else null,
    ).joinToString(", ")
    val tone: Color = when (historyTone(row.state)) {
        com.desolate.elisium.ui.downloads.Tone.Positive -> extras.positive
        com.desolate.elisium.ui.downloads.Tone.Negative -> extras.negative
        else -> extras.faint
    }
    val whenText = listOf(row.siteLabel, listOf(row.date, row.time).filter { it.isNotEmpty() }.joinToString(" "))
        .filter { it.isNotEmpty() }.joinToString(" · ")

    ElisiumCard(modifier = modifier, padding = PaddingValues(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = spoken },
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Thumbnail(null, row.siteLabel, width = 80.dp, height = 45.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(row.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(whenText, style = MaterialTheme.typography.bodySmall.merge(NumericStyle), color = extras.faint)
                Text(stateWord, style = MaterialTheme.typography.labelMedium, color = tone)
                row.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                if (row.fileStatus == FileStatus.Missing) {
                    Text(missing, style = MaterialTheme.typography.bodySmall, color = extras.negative)
                }
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            if (row.fileStatus != FileStatus.None) {
                val available = row.fileStatus == FileStatus.Available
                ElisiumTextButton(
                    text = stringResource(R.string.history_open),
                    onClick = onOpen,
                    enabled = available,
                    description = stringResource(R.string.history_open_for, row.title),
                )
                ElisiumTextButton(
                    text = stringResource(R.string.action_show_folder),
                    onClick = onShowInFolder,
                    enabled = available,
                    description = stringResource(R.string.action_show_folder_for, row.title),
                )
            }
            ElisiumTextButton(stringResource(R.string.history_again), onAgain, description = stringResource(R.string.history_again_for, row.title))
            ElisiumTextButton(stringResource(R.string.history_share), onShare, description = stringResource(R.string.history_share_for, row.title))
            ElisiumTextButton(stringResource(R.string.history_delete), onDelete, description = stringResource(R.string.history_delete_for, row.title))
        }
    }
}

@ShelfPreviews
@Composable
private fun HistoryRowPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HistoryRow(
                    HistoryRowModel(
                        1, "Monument Hill at dawn", "instagram.com", "https://instagram.com/p/x", "done", "22 Nov 2026", "/x.mp4",
                        FileStatus.Available, note = "Song cut to the post's snippet", filesTotal = 7, time = "10:38", siteLabel = "Instagram",
                    ),
                    {}, {}, {}, {}, {},
                )
                HistoryRow(
                    HistoryRowModel(2, "Sintel", "vimeo.com", "https://vimeo.com/1", "failed", "21 Nov 2026", null, FileStatus.None, siteLabel = "Vimeo"),
                    {}, {}, {}, {}, {},
                )
            }
        }
    }
}
