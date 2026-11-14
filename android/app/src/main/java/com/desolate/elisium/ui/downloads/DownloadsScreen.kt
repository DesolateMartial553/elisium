package com.desolate.elisium.ui.downloads

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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.components.AfterglowPreviews
import com.desolate.elisium.ui.components.ElisiumButton
import com.desolate.elisium.ui.components.ElisiumCard
import com.desolate.elisium.ui.components.ElisiumOutlinedButton
import com.desolate.elisium.ui.components.ElisiumTextButton
import com.desolate.elisium.ui.components.ElisiumTextField
import com.desolate.elisium.ui.components.EmptyState
import com.desolate.elisium.ui.components.GlowProgress
import com.desolate.elisium.ui.components.GlowState
import com.desolate.elisium.ui.components.StateChip
import com.desolate.elisium.ui.components.TintedBanner
import com.desolate.elisium.ui.components.enterRise
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.NumericStyle
import kotlinx.coroutines.launch

@Composable
fun DownloadsScreen(vm: QueueViewModel, input: String, onInputChange: (String) -> Unit, modifier: Modifier = Modifier) {
    val rows by vm.rows.collectAsStateWithLifecycle()
    val banner by vm.banner.collectAsStateWithLifecycle()
    val announcement by vm.announcement.collectAsStateWithLifecycle()
    val prompt by vm.cancelPrompt.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboard.current
    val reduced = ElisiumTheme.extras.reducedMotion
    // Rows that already played their enter animation (so scrolling back does not replay it).
    val seen = remember { HashSet<Int>() }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "add") {
            AddLinkRow(
                text = input,
                onTextChange = onInputChange,
                onAdd = { if (vm.addFromText(input)) onInputChange("") },
                onPaste = {
                    scope.launch {
                        val clip = clipboard.getClipEntry()?.clipData
                        val pasted = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).text?.toString() else null
                        if (!pasted.isNullOrBlank()) onInputChange(pasted)
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
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        if (rows.isEmpty()) {
            item(key = "empty") { EmptyState(stringResource(R.string.downloads_empty)) }
        }
        items(rows, key = { it.id }) { row ->
            val firstTime = seen.add(row.id)
            QueueRow(
                modifier = (if (reduced) Modifier else Modifier.animateItem()).enterRise(firstTime),
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
            confirmButton = { ElisiumTextButton(stringResource(R.string.cancel_confirm), vm::confirmCancel) },
            dismissButton = { ElisiumTextButton(stringResource(R.string.cancel_keep), vm::dismissCancel) },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AddLinkRow(text: String, onTextChange: (String) -> Unit, onAdd: () -> Unit, onPaste: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ElisiumTextField(
            value = text,
            onValueChange = onTextChange,
            label = stringResource(R.string.add_link_label),
            supportingText = stringResource(R.string.add_link_hint),
            maxLines = 4,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { if (text.isNotBlank()) onAdd() }),
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            ElisiumButton(stringResource(R.string.add_link_button), onAdd, enabled = text.isNotBlank())
            ElisiumOutlinedButton(stringResource(R.string.paste_button), onPaste)
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
    val tint = if (banner is Banner.ServiceProblem) ElisiumTheme.extras.error else ElisiumTheme.extras.warning
    TintedBanner(tint = tint, title = title, body = body)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun QueueRow(
    row: QueueRowModel,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val showPercent = row.percent != null && (row.state == "paused" || row.showProgress)
    val percentWord = if (showPercent) stringResource(R.string.percent_spoken, row.percent!!) else null
    val errorLine = row.errorMessage?.let { m -> listOfNotNull(m, row.errorFix).joinToString(" ") }
    val spoken = spokenRow(row.title, stateWord, percentWord, row, errorLine)
    val fraction = row.percent?.let { it / 100f }
    val glowState = when (row.state) {
        "paused" -> GlowState.Paused
        "done" -> GlowState.Done
        "failed" -> GlowState.Failed
        else -> GlowState.Active
    }

    ElisiumCard(modifier = modifier, active = row.state == "downloading") {
        // One node for a screen reader: "title, state, percent, speed, time left".
        Column(
            modifier = Modifier.fillMaxWidth().clearAndSetSemantics {
                contentDescription = spoken
                if (row.showProgress && fraction != null && !row.indeterminate) {
                    progressBarRangeInfo = ProgressBarRangeInfo(fraction, 0f..1f)
                }
            },
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(row.title, style = MaterialTheme.typography.titleMedium)
            // The state is always a word (inside the chip), never only a colour.
            StateChip(row.state, stateWord)
            if (row.showProgress) {
                GlowProgress(
                    fraction = if (row.indeterminate) null else fraction,
                    state = glowState,
                )
            }
            if (row.details.isNotEmpty()) {
                Text(
                    row.details,
                    style = MaterialTheme.typography.bodyMedium.merge(NumericStyle),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
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
                    ElisiumOutlinedButton(
                        text = stringResource(label),
                        onClick = click,
                        description = stringResource(description, row.title),
                    )
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
    details = if (state == "downloading") "2.1 MB/s - 12.4 MB of 80 MB - 40s left" else "",
    speedSpoken = "2.1 megabytes per second",
    etaSpoken = "40 seconds left",
    errorMessage = if (state == "failed") "Network problem." else null,
    errorFix = if (state == "failed") "Retry (auto-retry already ran)" else null,
    actions = validActions(state),
)

@AfterglowPreviews
@Composable
private fun QueueRowsPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                QueueRow(previewRow("downloading", 42), {}, {}, {}, {})
                QueueRow(previewRow("paused", 60), {}, {}, {}, {})
                QueueRow(previewRow("failed"), {}, {}, {}, {})
            }
        }
    }
}

@AfterglowPreviews
@Composable
private fun AddLinkPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                AddLinkRow("https://example.com/watch?v=1", {}, {}, {})
                BannerCard(Banner.WaitingForWifi)
                EmptyState(stringResource(R.string.downloads_empty))
            }
        }
    }
}
