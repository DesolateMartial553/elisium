# Brief 6B - Android redesign ("Afterglow")

The owner wants the apps to be much more beautiful and unique. Read `design/DESIGN.md`, `design/tokens.json`, `AGENTS.md` (the "Visual design" section applies), `briefs/phase5-d-android-screens.result.md`, then all of `android/app/src/main/java/com/desolate/elisium/ui/`. Inter fonts are already in `android/app/src/main/res/font/` (`inter_regular|medium|semibold|bold|extrabold.ttf`; licence `android/OFL-Inter.txt`).

Edit only under `android/` (code, resources, tests) and write `briefs/phase6-b-android-redesign.result.md`. Do not touch `desktop/` or `design/` (report token problems instead), do not commit or push, no emulator, no adb.

## Build
1. **Theme** `ui/theme/`: `Color.kt` (tokens as `Color` values, night + day, with a unit test that reads `../design/tokens.json` relative to the project root and asserts equality so drift fails), `Type.kt` (Inter `FontFamily` from `R.font`, Material 3 `Typography` per DESIGN.md sizes), `Shape.kt` (radii 10/16/24), `Theme.kt` rewritten: custom `ColorScheme` for night and day mapped from tokens (including `outline` = outlineStrong for controls), **dynamic colour OFF by default**, `ElisiumExtras` CompositionLocal exposing the glow colours, success/warning/error, raised, reduced-motion flag. Appearance setting System/Night/Day and Reduce motion in `SettingsRepository` (+ `SettingsStore`), defaults System/off, old stored data must still load. Edge-to-edge with correct status/nav bar icon contrast per theme.
2. **Components** `ui/components/`: `GlowProgress` (thick rounded bar, gradient fill glowA->glowB->glowC drawn with `drawBehind`/`Brush.horizontalGradient`, glowing leading cap via layered alpha circles or `BlurEffect` on API 31+ with a plain fallback below; paused = muted; done = success; failed = error; semantics `progressBarRangeInfo` + "N percent" unchanged; slow "breathing" of the cap while downloading using one `rememberInfiniteTransition`, disabled when reduced motion), `StateChip` (icon + word pill), `ElisiumCard` (raised, radius medium, 1dp outline, optional glow-gradient border when selected/active), `HorizonHeader` (wordmark "Elisium" with gradient text via `Brush` on `TextStyle`, faint glow band behind it fading to background), `EmptyState` (large soft glowing app-glyph drawn with Canvas + one warm sentence), `ElisiumButton` styles with >=48dp targets and a visible 2dp accent focus indicator. Use `animate*AsState` with the motion tokens (120/220/420 ms, ease-out); item enter animation (fade + 8dp rise) in lists via `Modifier.animateItem`/`AnimatedVisibility`; all gated by reduced motion (also honour `Settings.Global.ANIMATOR_DURATION_SCALE == 0`).
3. **Restyle every screen**: Downloads (horizon header, add-link field as a rounded glowing-focus input with Paste, cards with chips + GlowProgress + "speed - size - time left"), History (cards), Settings (grouped cards, rounded switches, Appearance + Reduce motion controls, presets as selectable cards), bottom navigation (rounded pill indicator in accent, labels always visible), dialogs, snackbars and banners (tinted from semantic tokens). Keep ALL existing semantics: content descriptions, merged row nodes, live regions with the 25% throttle, 48dp targets, font-scale-2.0 safe (no fixed heights).
4. **Launcher icon**: redraw `drawable` adaptive-icon foreground/background (and monochrome layer for themed icons, API 33) to match the new icon: arrow-into-tray glyph with the glow gradient on an ink-violet background with a faint horizon line. Vector drawables only (no PNG), keep resource names.
5. **Previews**: `@Preview`s for each component and screen in night and day and at fontScale 2.0 (they must compile; they are the owner's way to review in Android Studio).
6. **No new heavy dependencies** (no accompanist, no Lottie). Do not change `engine/`, `data/`, `backend/`, `service/` logic.

## Tests (JVM)
Existing 273 tests must pass (update only tests that asserted old visuals/strings; never weaken accessibility assertions). New: token-equality test; contrast of every token pair used by the `ColorScheme` mapping >= the limits in `design/contrast_check.py` (reimplement identically in Kotlin); appearance/reduce-motion settings defaults and round trip; pure helpers for glow geometry (fill width, cap position, clamping 0..100, NaN/null percent) with tests.

## Acceptance (paste real output)
```
python3 design/contrast_check.py | tail -1
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Lint must have zero errors (run it yourself). Report test counts, APK size. A first build may be OOM-killed on this 2-core machine: retry.

## Honesty
Nothing can be seen on a device or emulator here. Say plainly that looks, animation smoothness, blur on API 31+, themed-icon rendering and TalkBack are compile-verified only. Write the result file even if low on budget and list anything unfinished.
