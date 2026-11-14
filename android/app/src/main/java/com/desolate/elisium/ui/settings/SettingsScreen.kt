package com.desolate.elisium.ui.settings

import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.EngineState
import com.desolate.elisium.R
import com.desolate.elisium.settings.Appearance
import com.desolate.elisium.ui.components.AfterglowPreviews
import com.desolate.elisium.ui.components.ElisiumButton
import com.desolate.elisium.ui.components.ElisiumCard
import com.desolate.elisium.ui.components.ElisiumOutlinedButton
import com.desolate.elisium.ui.components.ElisiumTextField
import com.desolate.elisium.ui.components.TintedBanner
import com.desolate.elisium.ui.components.focusRing
import androidx.compose.ui.semantics.clearAndSetSemantics
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
        onAppearance = vm::setAppearance,
        onReduceMotion = vm::setReduceMotion,
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
    onAppearance: (Appearance) -> Unit = {},
    onReduceMotion: (Boolean) -> Unit = {},
) {
    Column(
        modifier = modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Section(R.string.settings_appearance) {
            Text(
                stringResource(R.string.settings_appearance_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            for (choice in Appearance.entries) {
                ChoiceCard(
                    label = stringResource(appearanceLabel(choice)),
                    selected = choice == state.appearance,
                    onSelect = { onAppearance(choice) },
                )
            }
            SwitchRow(
                stringResource(R.string.settings_reduce_motion),
                stringResource(R.string.settings_reduce_motion_help),
                state.reduceMotion,
                onReduceMotion,
            )
        }

        Section(R.string.settings_quality) {
            Text(
                stringResource(R.string.settings_quality_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            for (preset in presetChoices()) {
                ChoiceCard(label = preset.label, selected = preset.id == state.presetId, onSelect = { onPreset(preset.id) })
            }
        }

        Section(R.string.settings_concurrency) {
            Text(
                stringResource(R.string.settings_concurrency_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                ElisiumOutlinedButton(
                    text = "-",
                    onClick = onDecrease,
                    enabled = state.canDecrease,
                    description = stringResource(R.string.settings_concurrency_fewer),
                )
                val valueSpoken = stringResource(R.string.settings_concurrency_value, state.concurrency)
                Text(
                    text = state.concurrency.toString(),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.semantics {
                        liveRegion = LiveRegionMode.Polite
                        contentDescription = valueSpoken
                    },
                )
                ElisiumOutlinedButton(
                    text = "+",
                    onClick = onIncrease,
                    enabled = state.canIncrease,
                    description = stringResource(R.string.settings_concurrency_more),
                )
            }
        }

        Section(R.string.settings_speed) {
            ElisiumTextField(
                value = state.speedLimitText,
                onValueChange = onSpeedLimit,
                label = stringResource(R.string.settings_speed_label),
                singleLine = true,
                isError = state.speedLimitError != null,
                supportingText = stringResource(
                    if (state.speedLimitError != null) R.string.settings_speed_invalid else R.string.settings_speed_help,
                ),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
            )
        }

        Section(R.string.settings_network) {
            SwitchRow(stringResource(R.string.settings_wifi_only), stringResource(R.string.settings_wifi_only_help), state.wifiOnly, onWifiOnly)
            SwitchRow(stringResource(R.string.settings_notify), stringResource(R.string.settings_notify_help), state.notifyOnDone, onNotify)
            if (notificationsOff) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    TintedBanner(
                        tint = ElisiumTheme.extras.warning,
                        title = stringResource(R.string.settings_notifications_off_title),
                        body = stringResource(R.string.settings_notifications_off),
                    )
                    ElisiumButton(stringResource(R.string.settings_notifications_open), onOpenNotificationSettings)
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

private fun appearanceLabel(a: Appearance): Int = when (a) {
    Appearance.System -> R.string.appearance_system
    Appearance.Night -> R.string.appearance_night
    Appearance.Day -> R.string.appearance_day
}

/** A group: a section title (accent) above one raised card holding the controls. */
@Composable
private fun Section(titleRes: Int, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            stringResource(titleRes),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(horizontal = 4.dp).semantics { heading() },
        )
        ElisiumCard { content() }
    }
}

/** A selectable card (radio behaviour): the selected one gets the glow border. */
@Composable
private fun ChoiceCard(label: String, selected: Boolean, onSelect: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.medium,
        border = androidx.compose.foundation.BorderStroke(
            if (selected) 2.dp else 1.dp,
            if (selected) ElisiumTheme.extras.glowBrush() else androidx.compose.ui.graphics.SolidColor(ElisiumTheme.extras.outlineStrong),
        ),
        modifier = Modifier.fillMaxWidth()
            .focusRing(source, MaterialTheme.shapes.medium)
            .selectable(selected = selected, interactionSource = source, indication = null, onClick = onSelect, role = Role.RadioButton),
    ) {
        Row(
            Modifier.heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            if (selected) Text("\u2713", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clearAndSetSemantics { })
        }
    }
}

/** The whole row toggles, as one control with the Switch role; the label and help are its description. */
@Composable
private fun SwitchRow(label: String, help: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    val source = remember { MutableInteractionSource() }
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
            .focusRing(source, MaterialTheme.shapes.small)
            .toggleable(value = checked, interactionSource = source, indication = null, onValueChange = onChange, role = Role.Switch),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            Text(help, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(
            checked = checked,
            onCheckedChange = null,
            colors = SwitchDefaults.colors(
                checkedTrackColor = MaterialTheme.colorScheme.primary,
                checkedThumbColor = MaterialTheme.colorScheme.onPrimary,
                uncheckedTrackColor = ElisiumTheme.extras.raised,
                uncheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant,
                uncheckedBorderColor = MaterialTheme.colorScheme.outline,
            ),
        )
    }
}

@AfterglowPreviews
@Composable
private fun SettingsPreview() {
    ElisiumTheme {
        Surface(color = MaterialTheme.colorScheme.background) {
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
}
