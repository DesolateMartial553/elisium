package com.desolate.elisium.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.components.AfterglowPreviews
import com.desolate.elisium.ui.components.ElisiumCard
import com.desolate.elisium.ui.components.ElisiumOutlinedButton
import com.desolate.elisium.ui.components.ElisiumTextField
import com.desolate.elisium.ui.components.EmptyState
import com.desolate.elisium.ui.components.StateChip
import com.desolate.elisium.ui.components.enterRise
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme

@Composable
fun HistoryScreen(vm: HistoryViewModel, showMessage: (String) -> Unit, modifier: Modifier = Modifier) {
    val rows by vm.rows.collectAsStateWithLifecycle()
    val query by vm.query.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val noApp = stringResource(R.string.history_no_app)
    val shareTitle = stringResource(R.string.history_share_chooser)
    val reduced = ElisiumTheme.extras.reducedMotion
    val seen = remember { HashSet<Long>() }

    LaunchedEffect(Unit) { vm.reload() }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "search") {
            ElisiumTextField(
                value = query,
                onValueChange = vm::setQuery,
                label = stringResource(R.string.history_search_label),
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            )
        }
        if (rows.isEmpty()) {
            item(key = "empty") {
                EmptyState(stringResource(if (query.isBlank()) R.string.history_empty else R.string.history_no_matches))
            }
        }
        items(rows, key = { it.id }) { row ->
            val firstTime = seen.add(row.id)
            HistoryRow(
                modifier = (if (reduced) Modifier else Modifier.animateItem()).enterRise(firstTime),
                row = row,
                onOpen = { row.filePath?.let { if (!openFile(context, it)) showMessage(noApp) } },
                onShare = { shareLink(context, row.url, shareTitle) },
                onAgain = { vm.downloadAgain(row.url) },
                onDelete = { vm.deleteFromHistory(row.id) },
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HistoryRow(
    row: HistoryRowModel,
    onOpen: () -> Unit,
    onShare: () -> Unit,
    onAgain: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val missing = stringResource(R.string.history_file_missing)
    val spoken = listOfNotNull(
        row.title, row.site, stateWord, row.date.ifEmpty { null },
        if (row.fileStatus == FileStatus.Missing) missing else null,
    ).joinToString(", ")

    ElisiumCard(modifier = modifier) {
        Column(
            modifier = Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = spoken },
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(row.title, style = MaterialTheme.typography.titleMedium)
            Text(
                listOf(row.site, row.date).filter { it.isNotEmpty() }.joinToString(" - "),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            StateChip(row.state, stateWord)
            if (row.fileStatus == FileStatus.Missing) {
                Text(missing, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (row.fileStatus != FileStatus.None) {
                ElisiumOutlinedButton(
                    text = stringResource(R.string.history_open),
                    onClick = onOpen,
                    enabled = row.fileStatus == FileStatus.Available,
                    description = stringResource(R.string.history_open_for, row.title),
                )
            }
            ElisiumOutlinedButton(stringResource(R.string.history_share), onShare, description = stringResource(R.string.history_share_for, row.title))
            ElisiumOutlinedButton(stringResource(R.string.history_again), onAgain, description = stringResource(R.string.history_again_for, row.title))
            ElisiumOutlinedButton(stringResource(R.string.history_delete), onDelete, description = stringResource(R.string.history_delete_for, row.title))
        }
    }
}

@AfterglowPreviews
@Composable
private fun HistoryRowPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                HistoryRow(
                    HistoryRowModel(1, "Big Buck Bunny", "youtube.com", "https://youtube.com/watch?v=x", "done", "14 Nov 2026", "/x.mp4", FileStatus.Missing),
                    {}, {}, {}, {},
                )
                HistoryRow(
                    HistoryRowModel(2, "Sintel", "vimeo.com", "https://vimeo.com/1", "failed", "13 Nov 2026", null, FileStatus.None),
                    {}, {}, {}, {},
                )
                EmptyState(stringResource(R.string.history_empty))
            }
        }
    }
}
