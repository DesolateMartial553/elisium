package com.desolate.elisium.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.EngineState
import com.desolate.elisium.R
import com.desolate.elisium.ui.components.ElisiumMark
import com.desolate.elisium.ui.components.NoticeBanner
import com.desolate.elisium.ui.downloads.DownloadsScreen
import com.desolate.elisium.ui.history.HistoryScreen
import com.desolate.elisium.ui.permissions.PermissionHost
import com.desolate.elisium.ui.settings.InstagramLoginScreen
import com.desolate.elisium.ui.settings.SettingsScreen
import com.desolate.elisium.ui.theme.CardShape
import com.desolate.elisium.ui.theme.ElisiumTheme
import com.desolate.elisium.ui.theme.Motion
import com.desolate.elisium.ui.theme.Sizes
import kotlinx.coroutines.flow.Flow

/** The three screens. History and Settings are reached from the menu sheet; Back returns to Downloads. */
private enum class Screen(val titleRes: Int) {
    Downloads(R.string.tab_downloads),
    History(R.string.tab_history),
    Settings(R.string.tab_settings),
}

/** Scaffold with the 56dp top bar (mark, "Elisium", menu), the engine status line and the Snackbar host. Compile-verified only. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ElisiumShell(vm: ElisiumViewModel, engine: EngineState) {
    var screenIndex by rememberSaveable { mutableIntStateOf(0) }
    val screen = Screen.entries[screenIndex]
    var menuOpen by remember { mutableStateOf(false) }
    // A failed item's "Sign in" opens the login screen over the app, whatever screen is showing.
    var showLogin by remember { mutableStateOf(false) }
    // Kept for the Advanced section of Settings > Accounts (the cookies.txt import): set it to true to
    // open Settings with Accounts in view.
    var focusAccounts by remember { mutableStateOf(false) }
    val signIn = { showLogin = true }
    val signedInLine = stringResource(R.string.settings_accounts_signed_in)
    val signInFailedLine = stringResource(R.string.settings_accounts_sign_in_failed)
    // Lives outside AnimatedContent: the Downloads screen is disposed on a screen switch and would lose a half-typed link.
    var linkInput by rememberSaveable { mutableStateOf("") }
    val snackbar = remember { SnackbarHostState() }
    val hasUnfinished by vm.queue.hasUnfinished.collectAsStateWithLifecycle()

    SnackbarMessages(vm.queue.messages, snackbar)
    SnackbarMessages(vm.history.messages, snackbar)
    SnackbarMessages(vm.screenMessages, snackbar)
    PermissionHost(vm.queue.linksAdded)
    BackHandler(enabled = screen != Screen.Downloads && !showLogin) { screenIndex = Screen.Downloads.ordinal }

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            // While the sign-in page is up it is the only thing a screen reader may reach.
            modifier = Modifier.fillMaxSize().then(if (showLogin) Modifier.clearAndSetSemantics { } else Modifier),
            containerColor = MaterialTheme.colorScheme.background,
            topBar = { TopBar(onMenu = { menuOpen = true }) },
            snackbarHost = {
                SnackbarHost(snackbar) { data ->
                    Snackbar(
                        snackbarData = data,
                        shape = CardShape,
                        containerColor = ElisiumTheme.extras.raised,
                        contentColor = MaterialTheme.colorScheme.onSurface,
                        actionColor = MaterialTheme.colorScheme.onSurface,
                    )
                }
            },
        ) { padding ->
            Column(Modifier.padding(padding).consumeWindowInsets(padding).imePadding().fillMaxSize()) {
                EngineStatus(engine)
                if (screen != Screen.Downloads) {
                    Text(
                        text = stringResource(screen.titleRes),
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier.padding(horizontal = Sizes.GUTTER_PHONE.dp, vertical = 8.dp).semantics { heading() },
                    )
                }
                val reduced = ElisiumTheme.extras.reducedMotion
                // A screen change cross-fades over the base duration (instant when motion is reduced).
                AnimatedContent(
                    targetState = screen,
                    modifier = Modifier.weight(1f),
                    transitionSpec = {
                        (fadeIn(Motion.spec(Motion.BASE_MS, reduced)) togetherWith fadeOut(Motion.spec(Motion.FAST_MS, reduced)))
                    },
                    label = "screen",
                ) { current ->
                    when (current) {
                        Screen.Downloads -> DownloadsScreen(
                            vm.queue,
                            linkInput,
                            { linkInput = it },
                            Modifier.fillMaxSize(),
                            onSignIn = signIn,
                            showMessage = { vm.postMessage(it) },
                        )
                        Screen.History -> HistoryScreen(vm.history, showMessage = { vm.postMessage(it) }, modifier = Modifier.fillMaxSize())
                        Screen.Settings -> SettingsScreen(
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

        if (menuOpen) {
            ModalBottomSheet(
                onDismissRequest = { menuOpen = false },
                containerColor = ElisiumTheme.extras.raised,
                contentColor = MaterialTheme.colorScheme.onSurface,
            ) {
                Column(Modifier.padding(bottom = 16.dp)) {
                    for (s in Screen.entries) {
                        MenuRow(
                            label = stringResource(s.titleRes),
                            selected = s == screen,
                            onClick = { screenIndex = s.ordinal; menuOpen = false },
                        )
                    }
                    if (screen == Screen.Downloads) {
                        Spacer(Modifier.height(8.dp))
                        Text(
                            stringResource(R.string.menu_queue_group),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp).semantics { heading() },
                        )
                        MenuRow(
                            label = stringResource(R.string.menu_pause_all),
                            selected = false,
                            enabled = hasUnfinished,
                            onClick = { menuOpen = false; vm.queue.pauseAll() },
                        )
                        MenuRow(
                            label = stringResource(R.string.menu_cancel_all),
                            selected = false,
                            enabled = hasUnfinished,
                            onClick = { menuOpen = false; vm.queue.requestCancelAll() },
                        )
                    }
                }
            }
        }

        // Over the whole app so nothing of the queue is tappable mid sign-in.
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

/** 56dp bar on the ground colour: the mark, "Elisium" (18/700) and the menu button. No border, no shadow. */
@Composable
private fun TopBar(onMenu: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).height(Sizes.TOP_BAR_PHONE.dp)
            .padding(start = Sizes.GUTTER_PHONE.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ElisiumMark(size = 24.dp)
        Spacer(Modifier.width(9.dp))
        Text(
            text = stringResource(R.string.app_name),
            modifier = Modifier.weight(1f).semantics { heading() },
            style = MaterialTheme.typography.titleLarge.copy(fontSize = 18.sp),
        )
        IconButton(onClick = onMenu, modifier = Modifier.heightIn(min = Sizes.MIN_TARGET.dp)) {
            Icon(Icons.Filled.Menu, contentDescription = stringResource(R.string.menu_queue_actions))
        }
    }
}

/** A 52dp menu row. The current screen is shown only by its label being `text` rather than `muted` (no pill, no bar). */
@Composable
private fun MenuRow(label: String, selected: Boolean, onClick: () -> Unit, enabled: Boolean = true) {
    val color = when {
        !enabled -> ElisiumTheme.extras.faint
        selected -> MaterialTheme.colorScheme.onSurface
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(
        Modifier.fillMaxWidth().heightIn(min = 52.dp)
            .selectable(selected = selected, enabled = enabled, role = Role.Tab, onClick = onClick)
            .padding(horizontal = 24.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(label, style = MaterialTheme.typography.titleMedium, color = color)
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
            modifier = Modifier.fillMaxWidth().padding(horizontal = Sizes.GUTTER_PHONE.dp, vertical = 8.dp)
                .semantics { liveRegion = LiveRegionMode.Polite },
        )
        is EngineState.Failed -> NoticeBanner(
            tone = ElisiumTheme.extras.negative,
            title = stringResource(R.string.engine_failed_title),
            body = stringResource(R.string.engine_failed_body, engine.message),
            modifier = Modifier.padding(16.dp),
        )
        is EngineState.Ready -> Unit
    }
}
