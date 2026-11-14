package com.desolate.elisium.ui.settings

import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.EngineState
import com.desolate.elisium.R
import com.desolate.elisium.ui.permissions.showNotificationsOffNotice
import com.desolate.elisium.ui.theme.ElisiumTheme

@Composable
fun SettingsScreen(vm: SettingsViewModel, engine: EngineState, modifier: Modifier = Modifier) {
    val state by vm.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var notificationsEnabled by remember { mutableStateOf(true) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        notificationsEnabled = NotificationManagerCompat.from(context).areNotificationsEnabled()
    }
    SettingsContent(
        state = state,
        engine = engine,
        appVersion = remember { appVersionName(context) },
        notificationsOff = showNotificationsOffNotice(notificationsEnabled),
        onPreset = vm::setPreset,
        onDecrease = vm::decreaseConcurrency,
        onIncrease = vm::increaseConcurrency,
        onSpeedLimit = vm::setSpeedLimitText,
        onWifiOnly = vm::setWifiOnly,
        onNotify = vm::setNotifyOnDone,
        onOpenNotificationSettings = { openNotificationSettings(context) },
        modifier = modifier,
    )
}

private fun appVersionName(context: Context): String = try {
    context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""
} catch (_: Exception) {
    ""
}

private fun openNotificationSettings(context: Context) {
    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
}

@Composable
fun SettingsContent(
    state: SettingsUiState,
    engine: EngineState,
    appVersion: String,
    notificationsOff: Boolean,
    onPreset: (String) -> Unit,
    onDecrease: () -> Unit,
    onIncrease: () -> Unit,
    onSpeedLimit: (String) -> Unit,
    onWifiOnly: (Boolean) -> Unit,
    onNotify: (Boolean) -> Unit,
    onOpenNotificationSettings: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Section(R.string.settings_quality) {
            Text(stringResource(R.string.settings_quality_help), style = MaterialTheme.typography.bodyMedium)
            for (preset in presetChoices()) {
                Row(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                        .selectable(selected = preset.id == state.presetId, onClick = { onPreset(preset.id) }, role = Role.RadioButton),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = preset.id == state.presetId, onClick = null)
                    Text(preset.label, modifier = Modifier.padding(start = 12.dp), style = MaterialTheme.typography.bodyLarge)
                }
            }
        }

        Section(R.string.settings_concurrency) {
            Text(stringResource(R.string.settings_concurrency_help), style = MaterialTheme.typography.bodyMedium)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                val fewer = stringResource(R.string.settings_concurrency_fewer)
                OutlinedButton(
                    onClick = onDecrease,
                    enabled = state.canDecrease,
                    modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = fewer },
                ) { Text("-") }
                val valueSpoken = stringResource(R.string.settings_concurrency_value, state.concurrency)
                Text(
                    text = state.concurrency.toString(),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.semantics {
                        liveRegion = LiveRegionMode.Polite
                        contentDescription = valueSpoken
                    },
                )
                val more = stringResource(R.string.settings_concurrency_more)
                OutlinedButton(
                    onClick = onIncrease,
                    enabled = state.canIncrease,
                    modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = more },
                ) { Text("+") }
            }
        }

        Section(R.string.settings_speed) {
            OutlinedTextField(
                value = state.speedLimitText,
                onValueChange = onSpeedLimit,
                modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.settings_speed_label)) },
                singleLine = true,
                isError = state.speedLimitError != null,
                supportingText = {
                    Text(
                        stringResource(
                            if (state.speedLimitError != null) R.string.settings_speed_invalid else R.string.settings_speed_help,
                        ),
                    )
                },
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = KeyboardType.Ascii),
            )
        }

        Section(R.string.settings_network) {
            SwitchRow(stringResource(R.string.settings_wifi_only), stringResource(R.string.settings_wifi_only_help), state.wifiOnly, onWifiOnly)
            SwitchRow(stringResource(R.string.settings_notify), stringResource(R.string.settings_notify_help), state.notifyOnDone, onNotify)
            if (notificationsOff) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(stringResource(R.string.settings_notifications_off), style = MaterialTheme.typography.bodyMedium)
                        Button(onClick = onOpenNotificationSettings, modifier = Modifier.heightIn(min = 48.dp)) {
                            Text(stringResource(R.string.settings_notifications_open))
                        }
                    }
                }
            }
        }

        Section(R.string.settings_about) {
            Text(stringResource(R.string.about_version, appVersion.ifEmpty { "?" }), style = MaterialTheme.typography.bodyLarge)
            Text(
                text = when (engine) {
                    is EngineState.Ready -> stringResource(R.string.about_ytdlp, engine.ytDlpVersion)
                    EngineState.Starting -> stringResource(R.string.about_ytdlp_starting)
                    is EngineState.Failed -> stringResource(R.string.about_ytdlp_failed)
                },
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(stringResource(R.string.about_folder), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun Section(titleRes: Int, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(titleRes), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
        content()
    }
}

/** The whole row toggles, as one control with the Switch role; the label and help are its description. */
@Composable
private fun SwitchRow(label: String, help: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
            .toggleable(value = checked, onValueChange = onChange, role = Role.Switch),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            Text(help, style = MaterialTheme.typography.bodyMedium)
        }
        Switch(checked = checked, onCheckedChange = null)
    }
}

@Preview(showBackground = true)
@Composable
private fun SettingsPreview() {
    ElisiumTheme {
        SettingsContent(
            state = SettingsUiState(speedLimitText = "2m", speedLimitError = SpeedLimitError.Invalid),
            engine = EngineState.Ready("2026.10.01"),
            appVersion = "0.1.0",
            notificationsOff = true,
            onPreset = {}, onDecrease = {}, onIncrease = {}, onSpeedLimit = {},
            onWifiOnly = {}, onNotify = {}, onOpenNotificationSettings = {},
        )
    }
}
