# Brief 11D + 10E result - Android Night shelf and the multi-file screens

Status: implemented; JVM tests and `assembleDebug` pass. Not committed, not pushed, no emulator, no sudo.
**Every screen is "not seen on a device"** (no device or emulator was available; Compose code is compile-verified only).

## Acceptance (real output)
```
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug
> Task :app:assembleDebug
BUILD SUCCESSFUL in 5m 53s
45 actionable tasks: 21 executed, 24 up-to-date
EXIT 0
```
Test XML totals: `tests=600 skipped=0 failures=0 errors=0` (575 before + 25 new/changed net of the removed Glow/StateChip tests).
APK: `android/app/build/outputs/apk/debug/app-debug.apk` (74 MB).

`python3 design/nightshelf/contrast_check.py` -> `ALL PASS` (32 pairs, dark and light).

The first full run had 2 failing tests (my own: a "no violet" heuristic that flagged `negative`, and a wrong expectation in `sampleSizeFor`); both were fixed in the tests and the full run above is the second one.

## What was built
1. **Theme.** `ui/theme/Color.kt` (`ShelfPalette`, `NightPalette`/`DayPalette` = Night shelf tokens, dark/light follow system, Appearance override kept), `Theme.kt` (Material scheme from three lightness steps, surface tint off, `ElisiumExtras` with raised/control/faint/hue/track/tones), `Shape.kt` (`Radius`, `Sizes`, `TypeSizes` constants + shapes), `Motion.kt` (120/200 ms, `cubic-bezier(0.2,0,0,1)`, instant when reduced), `Type.kt` (Hanken Grotesk 400/600/700, sizes 20/15/24/14/13/12, tabular figures via `NumericStyle`). Hanken fonts copied to `res/font/hanken_grotesk_*.ttf`, OFL text at `res/raw/hanken_grotesk_ofl.txt` (a `.txt` inside `res/font` is not a legal resource). Inter files and `android/OFL-Inter.txt` deleted. Launch window colours `#000000` / `#F5F5F4`.
2. **Components** (rewritten flat: no gradient, glow, shadow, border): inverted-pill `ElisiumButton`, `ElisiumQuietButton` (raised pill), `ElisiumTextButton`, `ElisiumCard` (surface, radius 16), `ElisiumTextField` (44 dp pill), `FilterChip` (36 dp in a 44 dp target, 1.5 dp `hue` outline when selected), `FlatProgress` (4 dp, `hue`/`faint` on `track`), `ElisiumMark`, `EmptyState` (mark + sentence), `NoticeBanner`, `Thumbnail` (own loader: `HttpURLConnection` + `BitmapFactory` + LruCache, no new dependency; fallback is a `raised` block with the site name), focus ring = 2 dp `focus` outline with 2 dp offset. Deleted: `GlowProgress`, `GlowMath`, `HorizonHeader`, `StateChip` (+ their tests).
3. **Shell + Downloads.** 56 dp top bar (mark, "Elisium", menu button); menu is a bottom sheet with Downloads/History/Settings (current = label colour only) and Pause all / Cancel all on Downloads; Back returns to Downloads; bottom navigation removed. Link field + inverted "Download" pill (44 dp), "Paste" inside the empty field. Filter chips All/Downloading/Waiting/Failed/Done with counts (0 shown), same state grouping as desktop. Rows: 104x59 thumbnail, title 2 lines, meta line (`Site · format · size`, or `· 3 of 7 files`), note, 4 dp bar, percent 24/600 left and speed/time right, failed = reason in `negative` + one inverted pill (Sign in, else Retry; Retry kept as a quiet button beside Sign in), done = "Open" and "Show in folder". Spoken row text, "N percent" and live regions kept; the note is now spoken too. Pure logic in `downloads/QueueRows.kt` (`filterOf`, `filterCounts`, `applyFilter`, `rowMeta`, `queueTitle`, `toRowModel` additions), `etaText` and `siteName` in `Formatters.kt` (same tables as desktop).
4. **History + Settings.** History: search, site chips (derived from the rows), grouped by day (Today / Yesterday / "Thursday 19 November"), rows with note and state word, Open / Show in folder / Download again (+ Share link, Remove, kept). "Download again" = `queue.add(url, force = true)` through `downloadAgain()` in `ElisiumViewModel.kt`. Settings: five grouped lists on `surface` (Downloads, Photos and music, Accounts, Appearance, About); every earlier setting kept. "Photos and music" has the two real settings (Photos, song and video / Photos and song only / Photos only; Post's snippet / Full song) calling `setPhotoMode` / `setSongLength`; `SettingsUiState` and `SettingsViewModel` gained them.
5. **10E extras.** "Looking up the post..." title while a story tray, highlight, photo post or `/p/` link is queued/probing (rule: `routeFor(url) != YTDLP`); the "Already saved" note shows under the meta and in History; a done multi-file post's **Open goes to its folder** (`openFinished`/`openFolder` in `history/FileActions.kt`: Files app via `DocumentsContract` folder URI built from the file's `RELATIVE_PATH`, fallback to the system Downloads list; "Show in folder" does the same for single files).
6. **Owner subfolder.** `MediaStoreOutputStore` now overrides `publish(staged, name, subfolder)` and `existsInFolder(subfolder, id)`; `OutputNaming.kt` gained `relativePathFor` / `folderPathFor` (name cleaned by `safeFolderName`, so no `..` or extra level). Posts land in `Download/Elisium/<owner>/`; `publish(staged, name)` and `existsFor` stay flat (API 29+ MediaStore, API 26-28 legacy dir).
7. **Launcher icon.** Black square background; foreground and monochrome = the three-bar mark (last bar `#7CC4FF`), adaptive XML vectors.

## Tests
New: `ui/NightShelfQueueTest` (filter grouping, counts incl. zero, row text per state, multi-file meta, note, "Looking up the post...", thumbnail rule, meta/eta/site words), `ui/NightShelfHistoryTest` (row fields, day headings and grouping, site filter incl. view model, requeue wording, open target, folder ids, photo/song settings mapping and setters, progress and thumbnail sampling maths), `storage/OwnerFolderTest` (subfolder path building, no path escape). `ui/theme/TokensTest` rewritten: reads `design/nightshelf/tokens.json` at test time and checks colours (dark and light), radii, sizes, space, type sizes/family/weights, motion, contrast pairs (same as `contrast_check.py`), Material mapping, no violet, min 12 sp. `FakeSettingsStore` got the two setters. All previously existing tests pass unchanged.

## Deviations and notes
- No Compose UI test: the project has no Compose test dependencies. No screenshot-test spike (Paparazzi/Roborazzi are not in the offline Gradle cache).
- Edited outside the brief's literal list: deleted `android/OFL-Inter.txt` (an Inter file, the brief says to delete those), and added `downloadAgain` to `ui/ElisiumViewModel.kt` (inside `ui/`). `ElisiumApp.kt` untouched.
- Accessible name of the add button is now "Download" (string `add_link_button`), matching desktop; the add-link hint sentence is no longer shown (placeholder is "Paste a link from YouTube, Instagram, TikTok...", the old label is the spoken name).
- Reduce-motion help text changed (no "glow" wording). Previews now use `@ShelfPreviews` (Night, Day, Night font 2.0).
- Indeterminate progress (unknown percent, probing) shows only the empty track: no looping animation (DESIGN.md: no pulsing).
- History rows have no real thumbnail (history stores none): they show the site-name block at 80x45.
- Single-file rows "Show in folder" and multi-file "Open" depend on `MediaStore.RELATIVE_PATH` and the system Files app; on a phone without a handler it falls back to the Downloads list, then to a Snackbar line.

## Not seen on a device (all of it)
Downloads (empty, filters, every row state at 100% and 200% font), menu sheet, History, Settings, the launcher icon (incl. themed icon), the thumbnail loader (real CDN images, cleartext http blocked by the platform), Files-app folder opening on real devices, the owner-subfolder write path on API 26-28 and 29+, focus ring clipping inside the lists, `ModalBottomSheet` look with the Night shelf colours. Unchecked on real input: `BasicTextField` newline handling when a multi-line message is pasted (single-line field; `extractUrls` splits on whitespace).
