# Brief 6B result - Android redesign ("Afterglow")

## Commands run (to completion; JAVA_HOME=/usr/lib/jvm/java-21-openjdk, `nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g`)
- `python3 design/contrast_check.py | tail -1` -> `ALL PASS 0`
- `:app:testDebugUnitTest` -> BUILD SUCCESSFUL. 292 tests, 0 failures, 0 errors, 0 skipped (273 existing + 19 new).
- `:app:lintDebug` -> BUILD SUCCESSFUL, **0 errors, 18 warnings** (same dependency/version nags as before; no new categories).
- `:app:assembleDebug` -> BUILD SUCCESSFUL. APK `android/app/build/outputs/apk/debug/app-debug.apk` = 75,205,404 bytes (75.2 MB; was 73.9 MB, the rest is Inter fonts/new code).
- No emulator, adb, sudo, install, commit or push. `desktop/` and `design/` untouched.

## What was built (all under android/)
- Theme `ui/theme/`: `Color.kt` (night/day palettes from tokens), `Type.kt` (Inter, sizes 13-32sp, tabular-figure style), `Shape.kt` (10/16/24), `Motion.kt` (120/220/420 ms, ease-out, `isReducedMotion`), `Theme.kt` (custom ColorScheme for both themes with `outline` = outlineStrong, dynamic colour not used at all, `ElisiumExtras` CompositionLocal with glow/semantic/raised colours and reduced-motion flag, edge-to-edge with per-theme bar icon contrast via `enableEdgeToEdge`).
- Settings: `Appearance` (System/Night/Day) and `reduceMotion` added to `Settings`, `SettingsStore`, `SettingsRepository` (new DataStore keys; missing keys fall back to System/off, so old data loads), `SettingsViewModel`, Settings screen controls. `MainActivity` feeds them to the theme.
- Components `ui/components/`: `GlowProgress` (+ `GlowMath` pure geometry), `StateChip`, `ElisiumCard`, `HorizonHeader`, `EmptyState` (Canvas glyph), `ElisiumButton`/`OutlinedButton`/`TextButton` (>=48dp, 2dp accent focus ring via `focusRing`), `ElisiumTextField` (rounded, glowing focus halo), `TintedBanner`, `enterRise` (fade + 8dp rise), `AfterglowPreviews` (Night, Day, Night at font 2.0).
- Screens restyled: Downloads (horizon header, add-link field + Paste, cards with chip + GlowProgress + details line, tinted banners, empty state), History (cards, search field, empty state), Settings (grouped cards, Appearance and presets as selectable glow-border cards, rounded switches, Reduce motion), bottom nav (accent pill indicator, labels always shown), dialogs (themed via shapes/colours + ElisiumTextButton), snackbar (raised, glow border), tab cross-fade.
- Launcher icon: vector adaptive background (ink-violet gradient, faint horizon band/line), foreground (arrow-into-tray stroked with the glow gradient), monochrome layer (same silhouette). Resource names unchanged, no PNG.
- Previews for every component and for Downloads rows, History rows, Settings (night, day, font 2.0). They compile.

## Tests
New: `TokensTest` (token-file equality for both themes; all `contrast_check.py` pairs reimplemented in Kotlin for both themes; ColorScheme mapping contrast; typography >= 13sp; reduced-motion rule; appearance -> theme), `GlowMathTest` (clamping, NaN/null/inf, fill width, cap position), `StateChipTest`, `AppearanceSettingsTest` (defaults, stored round trip and unknown fallback, old settings, view-model round trip).
Changed tests (visual strings only): the detail line order is now "speed - size - time left" as the brief asks (was "size - speed - time left"); updated `FormattersTest`, `QueueUiTest`. `FakeSettingsStore` got the two new setters. No accessibility assertion was weakened.

## Semantics kept
Row text block is still one merged node with the same spoken sentence and `progressBarRangeInfo`; buttons keep "Pause <title>" style descriptions; live regions (announcement, banners, engine status, concurrency value) and the 25% announcer are untouched; switches/presets keep `Role.Switch`/`Role.RadioButton`; no fixed heights on text. Extras: section titles and header title are marked as headings.

## Honesty: compile-verified only
Nothing was seen on a device or emulator. Looks and spacing, animation smoothness (breathing cap, enter rise, tab fade, sliding indeterminate bar), the blurred cap glow on API 31+ (and the layered-circle fallback below), the focus ring, text-field halo, gradient text rendering, themed-icon (monochrome) rendering, gradient strokes in the launcher vector, edge-to-edge insets/IME padding, and TalkBack behaviour are all unverified. Layout at font scale 2.0 is designed (wrapping/FlowRow, no fixed text heights) but not seen.

## Notes / unfinished
- Token problems: none found; contrast check passes.
- Chip text uses the normal text colour (tint only on icon/border/background) so contrast does not depend on tints.
- Manifest theme is still the platform `Theme.Material.NoActionBar`, so the system window background shows briefly before Compose draws (not changed; manifest is outside the brief's scope of work).
- Cancel/permission dialog buttons use the new text button; dialog body/title styling comes from the theme (shape large, raised container).
- Paused chip icon is drawn on Canvas (Material "pause" icon is not in icons-core).
