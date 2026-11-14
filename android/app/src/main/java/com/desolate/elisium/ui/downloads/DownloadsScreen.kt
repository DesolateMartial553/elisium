package com.desolate.elisium.ui.downloads

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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme
import kotlinx.coroutines.launch

@Composable
fun DownloadsScreen(vm: QueueViewModel, modifier: Modifier = Modifier) {
    val rows by vm.rows.collectAsStateWithLifecycle()
    val banner by vm.banner.collectAsStateWithLifecycle()
    val announcement by vm.announcement.collectAsStateWithLifecycle()
    val prompt by vm.cancelPrompt.collectAsStateWithLifecycle()
    var input by rememberSaveable { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboard.current

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "add") {
            AddLinkRow(
                text = input,
                onTextChange = { input = it },
                onAdd = { if (vm.addFromText(input)) input = "" },
                onPaste = {
                    scope.launch {
                        val clip = clipboard.getClipEntry()?.clipData
                        val pasted = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).text?.toString() else null
                        if (!pasted.isNullOrBlank()) input = pasted
                    }
                },
            )
        }
        banner?.let { b -> item(key = "banner") { BannerCard(b) } }
        if (announcement.isNotEmpty()) {
            item(key = "announce") {
                Text(
                    text = announcement,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        if (rows.isEmpty()) {
            item(key = "empty") {
                Text(
                    text = stringResource(R.string.downloads_empty),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(vertical = 24.dp),
                )
            }
        }
        items(rows, key = { it.id }) { row ->
            QueueRow(
                row = row,
                onPause = { vm.pause(row.id) },
                onResume = { vm.resume(row.id) },
                onCancel = { vm.requestCancel(row.id) },
                onRetry = { vm.retry(row.id) },
            )
        }
    }

    prompt?.let { p ->
        AlertDialog(
            onDismissRequest = vm::dismissCancel,
            title = {
                Text(
                    when (p) {
                        is CancelPrompt.One -> stringResource(R.string.cancel_one_title)
                        CancelPrompt.All -> stringResource(R.string.cancel_all_title)
                    },
                )
            },
            text = {
                Text(
                    when (p) {
                        is CancelPrompt.One -> stringResource(R.string.cancel_one_body, p.title)
                        CancelPrompt.All -> stringResource(R.string.cancel_all_body)
                    },
                )
            },
            confirmButton = { TextButton(onClick = vm::confirmCancel) { Text(stringResource(R.string.cancel_confirm)) } },
            dismissButton = { TextButton(onClick = vm::dismissCancel) { Text(stringResource(R.string.cancel_keep)) } },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AddLinkRow(text: String, onTextChange: (String) -> Unit, onAdd: () -> Unit, onPaste: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = text,
            onValueChange = onTextChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text(stringResource(R.string.add_link_label)) },
            supportingText = { Text(stringResource(R.string.add_link_hint)) },
            maxLines = 4,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { if (text.isNotBlank()) onAdd() }),
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onAdd, enabled = text.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp)) {
                Text(stringResource(R.string.add_link_button))
            }
            OutlinedButton(onClick = onPaste, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(stringResource(R.string.paste_button))
            }
        }
    }
}

@Composable
fun BannerCard(banner: Banner) {
    val (title, body) = when (banner) {
        Banner.WaitingForWifi -> stringResource(R.string.banner_wifi_title) to stringResource(R.string.banner_wifi_body)
        is Banner.ServiceProblem -> stringResource(R.string.banner_service_title) to
            stringResource(R.string.banner_service_body, banner.message)
    }
    Card(modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text(body, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun QueueRow(
    row: QueueRowModel,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val showPercent = row.percent != null && (row.state == "paused" || row.showProgress)
    val percentWord = if (showPercent) stringResource(R.string.percent_spoken, row.percent!!) else null
    val errorLine = row.errorMessage?.let { m -> listOfNotNull(m, row.errorFix).joinToString(" ") }
    val spoken = spokenRow(row.title, stateWord, percentWord, row, errorLine)
    val fraction = row.percent?.let { it / 100f }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            // One node for a screen reader: "title, state, percent, speed, time left".
            Column(
                modifier = Modifier.fillMaxWidth().clearAndSetSemantics {
                    contentDescription = spoken
                    if (row.showProgress && fraction != null && !row.indeterminate) {
                        progressBarRangeInfo = ProgressBarRangeInfo(fraction, 0f..1f)
                    }
                },
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(row.title, style = MaterialTheme.typography.titleMedium)
                // The state is always a word, never only a colour.
                Text(stateWord, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                if (row.showProgress) {
                    if (row.indeterminate || fraction == null) {
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                    } else {
                        LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth())
                    }
                }
                if (row.details.isNotEmpty()) Text(row.details, style = MaterialTheme.typography.bodyMedium)
                if (errorLine != null) Text(errorLine, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
            }
            if (row.actions.isNotEmpty()) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (action in row.actions) {
                        val (label, description, click) = when (action) {
                            RowAction.Pause -> Triple(R.string.action_pause, R.string.action_pause_for, onPause)
                            RowAction.Resume -> Triple(R.string.action_resume, R.string.action_resume_for, onResume)
                            RowAction.Cancel -> Triple(R.string.action_cancel, R.string.action_cancel_for, onCancel)
                            RowAction.Retry -> Triple(R.string.action_retry, R.string.action_retry_for, onRetry)
                        }
                        val describe = stringResource(description, row.title)
                        OutlinedButton(
                            onClick = click,
                            modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = describe },
                        ) { Text(stringResource(label)) }
                    }
                }
            }
        }
    }
}

private fun previewRow(state: String, percent: Int? = null) = QueueRowModel(
    id = 1,
    title = "Big Buck Bunny - full film",
    state = state,
    percent = percent,
    showProgress = state == "downloading",
    indeterminate = state == "downloading" && percent == null,
    details = if (state == "downloading") "12.4 MB of 80 MB - 2.1 MB/s - 40s left" else "",
    speedSpoken = "2.1 megabytes per second",
    etaSpoken = "40 seconds left",
    errorMessage = if (state == "failed") "Network problem." else null,
    errorFix = if (state == "failed") "Retry (auto-retry already ran)" else null,
    actions = validActions(state),
)

@Preview(showBackground = true)
@Composable
private fun QueueRowDownloadingPreview() {
    ElisiumTheme { QueueRow(previewRow("downloading", 42), {}, {}, {}, {}) }
}

@Preview(showBackground = true, fontScale = 2f)
@Composable
private fun QueueRowFailedLargeTextPreview() {
    ElisiumTheme { QueueRow(previewRow("failed"), {}, {}, {}, {}) }
}
