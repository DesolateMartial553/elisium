package com.desolate.elisium.ui.downloads

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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.platform.LocalContext
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.R
import com.desolate.elisium.ui.components.ElisiumButton
import com.desolate.elisium.ui.components.ElisiumCard
import com.desolate.elisium.ui.components.ElisiumTextButton
import com.desolate.elisium.ui.components.ElisiumTextField
import com.desolate.elisium.ui.components.EmptyState
import com.desolate.elisium.ui.components.FilterChip
import com.desolate.elisium.ui.components.FlatProgress
import com.desolate.elisium.ui.components.NoticeBanner
import com.desolate.elisium.ui.components.ShelfPreviews
import com.desolate.elisium.ui.components.Thumbnail
import com.desolate.elisium.ui.components.enterRise
import com.desolate.elisium.ui.history.openFinished
import com.desolate.elisium.ui.history.openFolder
import com.desolate.elisium.ui.stateLabelRes
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.NumericStyle
import com.desolate.elisium.ui.theme.Sizes
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun filterLabel(filter: QueueFilter): String = stringResource(
    when (filter) {
        QueueFilter.All -> R.string.filter_all
        QueueFilter.Downloading -> R.string.filter_downloading
        QueueFilter.Waiting -> R.string.filter_waiting
        QueueFilter.Failed -> R.string.filter_failed
        QueueFilter.Done -> R.string.filter_done
    },
)

@Composable
fun DownloadsScreen(
    vm: QueueViewModel,
    input: String,
    onInputChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    onSignIn: () -> Unit = {},
    showMessage: (String) -> Unit = {},
) {
    val allRows by vm.rows.collectAsStateWithLifecycle()
    val rows by vm.visibleRows.collectAsStateWithLifecycle()
    val counts by vm.counts.collectAsStateWithLifecycle()
    val filter by vm.filter.collectAsStateWithLifecycle()
    val banner by vm.banner.collectAsStateWithLifecycle()
    val announcement by vm.announcement.collectAsStateWithLifecycle()
    val prompt by vm.cancelPrompt.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboard.current
    val context = LocalContext.current
    val reduced = ElisiumTheme.extras.reducedMotion
    val noApp = stringResource(R.string.history_no_app)
    val noFolder = stringResource(R.string.folder_no_app)
    // Rows that already played their enter animation (so scrolling back does not replay it).
    val seen = remember { HashSet<Int>() }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 16.dp),
        verticalArrangement = Arrangement.spacedBy(Sizes.GAP.dp),
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
                modifier = Modifier.padding(horizontal = Sizes.GUTTER_PHONE.dp),
            )
        }
        item(key = "chips") {
            LazyRow(
                contentPadding = PaddingValues(horizontal = Sizes.GUTTER_PHONE.dp),
                horizontalArrangement = Arrangement.spacedBy(Sizes.GAP.dp),
            ) {
                items(QueueFilter.entries, key = { it.key }) { f ->
                    val label = filterLabel(f)
                    val count = counts[f] ?: 0
                    FilterChip(
                        label = label,
                        count = count,
                        selected = f == filter,
                        onClick = { vm.setFilter(f) },
                        description = stringResource(R.string.filter_spoken, label, count),
                    )
                }
            }
        }
        banner?.let { b -> item(key = "banner") { BannerCard(b, Modifier.padding(horizontal = Sizes.GUTTER_PHONE.dp)) } }
        if (announcement.isNotEmpty()) {
            item(key = "announce") {
                Text(
                    text = announcement,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = Sizes.GUTTER_PHONE.dp)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        if (allRows.isEmpty()) {
            item(key = "empty") { EmptyState(stringResource(R.string.downloads_empty)) }
        } else if (rows.isEmpty()) {
            item(key = "empty-filter") { EmptyState(stringResource(R.string.filter_empty)) }
        }
        items(rows, key = { it.id }) { row ->
            val firstTime = seen.add(row.id)
            QueueRow(
                modifier = (if (reduced) Modifier else Modifier.animateItem()).enterRise(firstTime)
                    .padding(horizontal = Sizes.GUTTER_PHONE.dp),
                row = row,
                onPause = { vm.pause(row.id) },
                onResume = { vm.resume(row.id) },
                onCancel = { vm.requestCancel(row.id) },
                onRetry = { vm.retry(row.id) },
                onSignIn = onSignIn,
                onOpen = { path -> if (!openFinished(context, path, row.multiFile)) showMessage(if (row.multiFile) noFolder else noApp) },
                onShowInFolder = { path -> if (!openFolder(context, path)) showMessage(noFolder) },
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

/** The link field (a 44dp pill) and the inverted Download pill. "Paste" sits inside the field while it is empty. */
@Composable
fun AddLinkRow(
    text: String,
    onTextChange: (String) -> Unit,
    onAdd: () -> Unit,
    onPaste: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Sizes.GAP.dp), verticalAlignment = Alignment.Top) {
        ElisiumTextField(
            value = text,
            onValueChange = onTextChange,
            label = stringResource(R.string.add_link_label),
            placeholder = stringResource(R.string.add_link_placeholder),
            singleLine = true,
            modifier = Modifier.weight(1f),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { if (text.isNotBlank()) onAdd() }),
            trailing = if (text.isEmpty()) {
                { ElisiumTextButton(stringResource(R.string.paste_short), onPaste, description = stringResource(R.string.paste_button)) }
            } else {
                null
            },
        )
        ElisiumButton(stringResource(R.string.add_link_button), onAdd, enabled = text.isNotBlank())
    }
}

@Composable
fun BannerCard(banner: Banner, modifier: Modifier = Modifier) {
    val (title, body) = when (banner) {
        Banner.WaitingForWifi -> stringResource(R.string.banner_wifi_title) to stringResource(R.string.banner_wifi_body)
        is Banner.ServiceProblem -> stringResource(R.string.banner_service_title) to
            stringResource(R.string.banner_service_body, banner.message)
    }
    val tone = if (banner is Banner.ServiceProblem) ElisiumTheme.extras.negative else ElisiumTheme.extras.warning
    NoticeBanner(tone = tone, title = title, body = body, modifier = modifier)
}

@Composable
private fun toneColor(tone: Tone): Color = when (tone) {
    Tone.Positive -> ElisiumTheme.extras.positive
    Tone.Negative -> ElisiumTheme.extras.negative
    Tone.Faint -> ElisiumTheme.extras.faint
    Tone.Muted -> MaterialTheme.colorScheme.onSurfaceVariant
}

/**
 * One download: a 104x59 thumbnail, the title (two lines), a meta line, an optional note, the 4dp bar, then the
 * percent / state word on the left and speed and time left on the right. The words always say the state.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun QueueRow(
    row: QueueRowModel,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    onSignIn: () -> Unit = {},
    onOpen: (String) -> Unit = {},
    onShowInFolder: (String) -> Unit = {},
) {
    val stateWord = stringResource(stateLabelRes(row.state))
    val showPercent = row.percent != null && (row.state == "paused" || row.showProgress)
    val percentWord = if (showPercent) stringResource(R.string.percent_spoken, row.percent!!) else null
    val errorLine = row.errorMessage?.let { m -> listOfNotNull(m, row.errorFix).joinToString(" ") }
    val spoken = spokenRow(row.title, stateWord, percentWord, row, errorLine)
    // After 10 quiet seconds a starting row says why ("Starting... Signing in"); one tick a second while it waits.
    var nowMs by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(row.startingSince) {
        val since = row.startingSince ?: return@LaunchedEffect
        while (true) {
            nowMs = System.currentTimeMillis()
            if (nowMs - since >= STALL_AFTER_MS) break
            delay(1_000L)
        }
    }
    val side = row.sideAt(nowMs)
    val fraction = row.percent?.let { it / 100f }
    val extras = ElisiumTheme.extras

    ElisiumCard(modifier = modifier, padding = PaddingValues(10.dp)) {
        // One node for a screen reader: "title, state, percent, speed, time left, error, note".
        Row(
            modifier = Modifier.fillMaxWidth().clearAndSetSemantics {
                contentDescription = spoken
                if (row.showProgress && fraction != null && !row.indeterminate) {
                    progressBarRangeInfo = ProgressBarRangeInfo(fraction, 0f..1f)
                }
            },
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Thumbnail(row.thumbnail, row.site)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(row.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (row.meta.isNotEmpty()) {
                    Text(row.meta, style = MaterialTheme.typography.bodySmall.merge(NumericStyle), color = extras.faint)
                }
                row.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                if (row.bar != BarKind.None) FlatProgress(if (row.indeterminate) null else fraction, paused = row.bar == BarKind.Paused)
                if (errorLine != null) {
                    Text(errorLine, style = MaterialTheme.typography.bodySmall, color = extras.negative)
                } else if (row.figure.isNotEmpty() || row.stateWord.isNotEmpty() || side.isNotEmpty()) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.Bottom,
                    ) {
                        if (row.figure.isNotEmpty()) {
                            Text(row.figure, style = MaterialTheme.typography.headlineSmall.merge(NumericStyle))
                        } else if (row.stateWord.isNotEmpty()) {
                            Text(row.stateWord, style = MaterialTheme.typography.titleMedium, color = toneColor(row.tone))
                        }
                        if (side.isNotEmpty()) {
                            Text(
                                side,
                                style = MaterialTheme.typography.labelSmall.merge(NumericStyle),
                                color = if (row.tone == Tone.Faint) extras.faint else MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.End,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }
        }
        val fix = if (RowAction.SignIn in row.actions) RowAction.SignIn else if (RowAction.Retry in row.actions) RowAction.Retry else null
        if (row.actions.isNotEmpty() || row.canOpen) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (action in row.actions) {
                    val (label, description, click) = when (action) {
                        RowAction.Pause -> Triple(R.string.action_pause, R.string.action_pause_for, onPause)
                        RowAction.Resume -> Triple(R.string.action_resume, R.string.action_resume_for, onResume)
                        RowAction.Cancel -> Triple(R.string.action_cancel, R.string.action_cancel_for, onCancel)
                        RowAction.Retry -> Triple(R.string.action_retry, R.string.action_retry_for, onRetry)
                        RowAction.SignIn -> Triple(R.string.action_sign_in, R.string.action_sign_in_for, onSignIn)
                    }
                    if (action == fix) {
                        // The one inverted pill: the fix for a failed or cancelled row.
                        ElisiumButton(stringResource(label), click, description = stringResource(description, row.title))
                    } else {
                        ElisiumTextButton(stringResource(label), click, description = stringResource(description, row.title))
                    }
                }
                val path = row.filePath
                if (row.canOpen && path != null) {
                    ElisiumTextButton(
                        stringResource(R.string.action_open),
                        { onOpen(path) },
                        description = stringResource(R.string.action_open_for, row.title),
                    )
                    ElisiumTextButton(
                        stringResource(R.string.action_show_folder),
                        { onShowInFolder(path) },
                        description = stringResource(R.string.action_show_folder_for, row.title),
                    )
                }
            }
        }
    }
}

private fun previewRow(state: String, percent: Int? = null, note: String? = null) = QueueRowModel(
    id = 1,
    title = "Big Buck Bunny - the full film, restored",
    state = state,
    percent = percent,
    showProgress = state == "downloading",
    indeterminate = false,
    details = "",
    speedSpoken = "",
    etaSpoken = "",
    errorMessage = if (state == "failed") "Instagram sign-in has expired" else null,
    errorFix = null,
    needsSignIn = state == "failed",
    actions = validActions(state, if (state == "failed") "session_expired" else null),
    site = "YouTube",
    meta = "YouTube · 1080p MP4 · 648.5 MB",
    note = note,
    figure = if (percent != null) "$percent%" else "",
    stateWord = if (state == "done") "Done" else "",
    side = if (state == "downloading") "4.2 MB/s · 1 min 37 s left" else "",
    tone = if (state == "done") Tone.Positive else Tone.Muted,
    bar = if (state == "downloading") BarKind.Hue else BarKind.None,
    filePath = if (state == "done") "/x.mp4" else null,
    canOpen = state == "done",
)

@ShelfPreviews
@Composable
private fun QueueRowsPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                QueueRow(previewRow("downloading", 42), {}, {}, {}, {})
                QueueRow(previewRow("done", note = "Already saved"), {}, {}, {}, {})
                QueueRow(previewRow("failed"), {}, {}, {}, {})
            }
        }
    }
}
