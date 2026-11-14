package com.desolate.elisium.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.EngineState
import com.desolate.elisium.R
import com.desolate.elisium.ui.downloads.DownloadsScreen
import com.desolate.elisium.ui.history.HistoryScreen
import com.desolate.elisium.ui.permissions.PermissionHost
import com.desolate.elisium.ui.settings.SettingsScreen
import kotlinx.coroutines.flow.Flow

private enum class Tab(val titleRes: Int, val icon: ImageVector) {
    Downloads(R.string.tab_downloads, Icons.AutoMirrored.Filled.List),
    History(R.string.tab_history, Icons.Filled.DateRange),
    Settings(R.string.tab_settings, Icons.Filled.Settings),
}

/** Scaffold with the bottom navigation, the engine status line and the Snackbar host. Compile-verified only. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ElisiumShell(vm: ElisiumViewModel, engine: EngineState) {
    var tabIndex by rememberSaveable { mutableIntStateOf(0) }
    val tab = Tab.entries[tabIndex]
    val snackbar = remember { SnackbarHostState() }
    val hasUnfinished by vm.queue.hasUnfinished.collectAsStateWithLifecycle()

    SnackbarMessages(vm.queue.messages, snackbar)
    SnackbarMessages(vm.history.messages, snackbar)
    SnackbarMessages(vm.screenMessages, snackbar)
    PermissionHost(vm.queue.linksAdded)

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(tab.titleRes)) },
                actions = {
                    if (tab == Tab.Downloads) {
                        var open by remember { mutableStateOf(false) }
                        IconButton(onClick = { open = true }) {
                            Icon(Icons.Filled.MoreVert, contentDescription = stringResource(R.string.menu_queue_actions))
                        }
                        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.menu_pause_all)) },
                                enabled = hasUnfinished,
                                onClick = { open = false; vm.queue.pauseAll() },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.menu_cancel_all)) },
                                enabled = hasUnfinished,
                                onClick = { open = false; vm.queue.requestCancelAll() },
                            )
                        }
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                for (t in Tab.entries) {
                    NavigationBarItem(
                        selected = t == tab,
                        onClick = { tabIndex = t.ordinal },
                        icon = { Icon(t.icon, contentDescription = null) },
                        label = { Text(stringResource(t.titleRes)) },
                        alwaysShowLabel = true,
                    )
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            EngineStatus(engine)
            when (tab) {
                Tab.Downloads -> DownloadsScreen(vm.queue, Modifier.weight(1f))
                Tab.History -> HistoryScreen(vm.history, showMessage = { vm.postMessage(it) }, modifier = Modifier.weight(1f))
                Tab.Settings -> SettingsScreen(vm.settings, engine, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun SnackbarMessages(messages: Flow<String>, host: SnackbarHostState) {
    LaunchedEffect(messages) {
        messages.collect { line ->
            host.currentSnackbarData?.dismiss()
            host.showSnackbar(line)
        }
    }
}

@Composable
private fun EngineStatus(engine: EngineState) {
    when (engine) {
        EngineState.Starting -> Text(
            text = stringResource(R.string.engine_starting),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)
                .semantics { liveRegion = LiveRegionMode.Polite },
        )
        is EngineState.Failed -> Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp).semantics { liveRegion = LiveRegionMode.Polite },
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(stringResource(R.string.engine_failed_title), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.error)
            Text(stringResource(R.string.engine_failed_body, engine.message), style = MaterialTheme.typography.bodyMedium)
        }
        is EngineState.Ready -> Unit
    }
}
