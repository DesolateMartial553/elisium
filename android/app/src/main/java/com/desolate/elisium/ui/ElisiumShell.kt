package com.desolate.elisium.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Snackbar
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import com.desolate.elisium.ui.components.HorizonHeader
import com.desolate.elisium.ui.components.TintedBanner
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
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
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.EngineState
import com.desolate.elisium.R
import com.desolate.elisium.ui.downloads.DownloadsScreen
import com.desolate.elisium.ui.history.HistoryScreen
import com.desolate.elisium.ui.permissions.PermissionHost
import com.desolate.elisium.ui.settings.InstagramLoginScreen
import com.desolate.elisium.ui.settings.SettingsScreen
import kotlinx.coroutines.flow.Flow

private enum class Tab(val titleRes: Int, val icon: ImageVector) {
    Downloads(R.string.tab_downloads, Icons.AutoMirrored.Filled.List),
    History(R.string.tab_history, Icons.Filled.DateRange),
    Settings(R.string.tab_settings, Icons.Filled.Settings),
}

/** Scaffold with the bottom navigation, the engine status line and the Snackbar host. Compile-verified only. */
@Composable
fun ElisiumShell(vm: ElisiumViewModel, engine: EngineState) {
    var tabIndex by rememberSaveable { mutableIntStateOf(0) }
    val tab = Tab.entries[tabIndex]
    // A failed item's "Sign in" opens the login screen over the app, whatever tab is showing.
    var showLogin by remember { mutableStateOf(false) }
    // Kept for the Advanced section of Settings > Accounts (the cookies.txt import): set it to true to
    // open Settings with Accounts in view.
    var focusAccounts by remember { mutableStateOf(false) }
    val signIn = { showLogin = true }
    val signedInLine = stringResource(R.string.settings_accounts_signed_in)
    val signInFailedLine = stringResource(R.string.settings_accounts_sign_in_failed)
    // Lives outside AnimatedContent: the Downloads screen is disposed on a tab switch and would lose a half-typed link.
    var linkInput by rememberSaveable { mutableStateOf("") }
    val snackbar = remember { SnackbarHostState() }
    val hasUnfinished by vm.queue.hasUnfinished.collectAsStateWithLifecycle()

    SnackbarMessages(vm.queue.messages, snackbar)
    SnackbarMessages(vm.history.messages, snackbar)
    SnackbarMessages(vm.screenMessages, snackbar)
    PermissionHost(vm.queue.linksAdded)

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            // While the sign-in page is up it is the only thing a screen reader may reach.
            modifier = Modifier.fillMaxSize().then(if (showLogin) Modifier.clearAndSetSemantics { } else Modifier),
            containerColor = MaterialTheme.colorScheme.background,
            topBar = {
                HorizonHeader(
                    title = stringResource(if (tab == Tab.Downloads) R.string.app_name else tab.titleRes),
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
                val line = ElisiumTheme.extras.outline
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.surface,
                    tonalElevation = 0.dp,
                    modifier = Modifier.drawBehind {
                        drawLine(line, Offset(0f, 0f), Offset(size.width, 0f), strokeWidth = 1.dp.toPx())
                    },
                ) {
                    for (t in Tab.entries) {
                        NavigationBarItem(
                            selected = t == tab,
                            onClick = { tabIndex = t.ordinal },
                            icon = { Icon(t.icon, contentDescription = null) },
                            label = { Text(stringResource(t.titleRes), style = MaterialTheme.typography.labelMedium) },
                            alwaysShowLabel = true,
                            colors = NavigationBarItemDefaults.colors(
                                indicatorColor = MaterialTheme.colorScheme.primary,
                                selectedIconColor = MaterialTheme.colorScheme.onPrimary,
                                selectedTextColor = MaterialTheme.colorScheme.onSurface,
                                unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                                unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            ),
                        )
                    }
                }
            },
            snackbarHost = {
                SnackbarHost(snackbar) { data ->
                    Snackbar(
                        snackbarData = data,
                        shape = MaterialTheme.shapes.medium,
                        containerColor = ElisiumTheme.extras.raised,
                        contentColor = MaterialTheme.colorScheme.onSurface,
                        actionColor = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.border(1.dp, ElisiumTheme.extras.glowBrush(), MaterialTheme.shapes.medium),
                    )
                }
            },
        ) { padding ->
            Column(Modifier.padding(padding).consumeWindowInsets(padding).imePadding().fillMaxSize()) {
                EngineStatus(engine)
                val reduced = ElisiumTheme.extras.reducedMotion
                // Tab change cross-fades over the base duration (instant when motion is reduced).
                AnimatedContent(
                    targetState = tab,
                    modifier = Modifier.weight(1f),
                    transitionSpec = {
                        (fadeIn(Motion.spec(Motion.BASE_MS, reduced)) togetherWith fadeOut(Motion.spec(Motion.FAST_MS, reduced)))
                    },
                    label = "tab",
                ) { current ->
                    when (current) {
                        Tab.Downloads -> DownloadsScreen(
                            vm.queue,
                            linkInput,
                            { linkInput = it },
                            Modifier.fillMaxSize(),
                            onSignIn = signIn,
                        )
                        Tab.History -> HistoryScreen(vm.history, showMessage = { vm.postMessage(it) }, modifier = Modifier.fillMaxSize())
                        Tab.Settings -> SettingsScreen(
                            vm.settings,
                            engine,
                            Modifier.fillMaxSize(),
                            focusAccounts = focusAccounts,
                            onAccountsShown = { focusAccounts = false },
                            onSignIn = signIn,
                        )
                    }
                }
            }
        }

    // Over the whole app (bottom bar included) so nothing of the queue is tappable mid sign-in.
    if (showLogin) {
        InstagramLoginScreen(
            onSession = { text ->
                val stored = vm.settings.importCookies(text)
                vm.postMessage(if (stored) signedInLine else signInFailedLine)
            },
            onClose = { showLogin = false },
            modifier = Modifier.fillMaxSize(),
        )
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
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)
                .semantics { liveRegion = LiveRegionMode.Polite },
        )
        is EngineState.Failed -> TintedBanner(
            tint = ElisiumTheme.extras.error,
            title = stringResource(R.string.engine_failed_title),
            body = stringResource(R.string.engine_failed_body, engine.message),
            modifier = Modifier.padding(16.dp),
        )
        is EngineState.Ready -> Unit
    }
}
