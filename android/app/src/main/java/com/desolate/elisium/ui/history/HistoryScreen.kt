package com.desolate.elisium.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme

@Composable
fun HistoryScreen(vm: HistoryViewModel, showMessage: (String) -> Unit, modifier: Modifier = Modifier) {
    val rows by vm.rows.collectAsStateWithLifecycle()
    val query by vm.query.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val noApp = stringResource(R.string.history_no_app)
    val shareTitle = stringResource(R.string.history_share_chooser)

    LaunchedEffect(Unit) { vm.reload() }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "search") {
            OutlinedTextField(
                value = query,
                onValueChange = vm::setQuery,
                modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.history_search_label)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            )
        }
        if (rows.isEmpty()) {
            item(key = "empty") {
                Text(
                    text = stringResource(if (query.isBlank()) R.string.history_empty else R.string.history_no_matches),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(vertical = 24.dp),
                )
            }
        }
        items(rows, key = { it.id }) { row ->
            HistoryRow(
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
fun HistoryRow(row: HistoryRowModel, onOpen: () -> Unit, onShare: () -> Unit, onAgain: () -> Unit, onDelete: () -> Unit) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val missing = stringResource(R.string.history_file_missing)
    val spoken = listOfNotNull(
        row.title, row.site, stateWord, row.date.ifEmpty { null },
        if (row.fileStatus == FileStatus.Missing) missing else null,
    ).joinToString(", ")

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(
                modifier = Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = spoken },
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(row.title, style = MaterialTheme.typography.titleMedium)
                Text(row.site, style = MaterialTheme.typography.bodyMedium)
                Text(
                    listOf(stateWord, row.date).filter { it.isNotEmpty() }.joinToString(" - "),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                if (row.fileStatus == FileStatus.Missing) {
                    Text(missing, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (row.fileStatus != FileStatus.None) {
                    val openDescription = stringResource(R.string.history_open_for, row.title)
                    OutlinedButton(
                        onClick = onOpen,
                        enabled = row.fileStatus == FileStatus.Available,
                        modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = openDescription },
                    ) { Text(stringResource(R.string.history_open)) }
                }
                val shareDescription = stringResource(R.string.history_share_for, row.title)
                OutlinedButton(
                    onClick = onShare,
                    modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = shareDescription },
                ) { Text(stringResource(R.string.history_share)) }
                val againDescription = stringResource(R.string.history_again_for, row.title)
                OutlinedButton(
                    onClick = onAgain,
                    modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = againDescription },
                ) { Text(stringResource(R.string.history_again)) }
                val deleteDescription = stringResource(R.string.history_delete_for, row.title)
                OutlinedButton(
                    onClick = onDelete,
                    modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = deleteDescription },
                ) { Text(stringResource(R.string.history_delete)) }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun HistoryRowPreview() {
    ElisiumTheme {
        HistoryRow(
            HistoryRowModel(1, "Big Buck Bunny", "youtube.com", "https://youtube.com/watch?v=x", "done", "14 Nov 2026", "/x.mp4", FileStatus.Missing),
            {}, {}, {}, {},
        )
    }
}
