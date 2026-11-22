# Brief 11D + 10E - Android: Night shelf restyle and the multi-file screens (one pass over the same files)

Read `AGENTS.md`, `design/nightshelf/DESIGN.md` and `tokens.json` (the target; phone sizes: topBarPhone 56, controlPhone 44,
thumbPhone 104x59, gutterPhone 16, minTarget 44, chips 36), then the desktop results to mirror the content:
`briefs/phase11-c1-desktop-nightshelf-shell.result.md`, `briefs/phase11-c2-desktop-nightshelf-pages.result.md`,
`briefs/phase10-c-desktop-multifile-screens.result.md`, and `briefs/phase10-d-android-media-engine.result.md` (the snapshot
fields and settings setters the UI now reads). The approved phone mockup: https://claude.ai/artifact/As1YVj8NtnAJdqVkQFKR3Q
(source `.taste-skill/mock/pub/phone.html`; History/Settings: `.taste-skill/mock/pub/screens.html`).
Edit only under `android/app/src/main/java/com/desolate/elisium/ui/**`, `android/app/src/main/res/` (fonts, icons, strings,
theme XML), `android/app/src/main/java/com/desolate/elisium/storage/` (ONLY for the owner-subfolder fix below), their tests
under `android/app/src/test/`, and write `briefs/phase11-d-android-nightshelf-and-10e-screens.result.md`.
No engine changes, no desktop, no commit/push, no sudo, no emulator, no new dependencies (the offline Gradle cache has no
screenshot-testing library, so skip the Paparazzi/Roborazzi spike and say so).
Gradle: `nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g ...` with
`JAVA_HOME=/usr/lib/jvm/java-21-openjdk` (there is no gradlew); one Gradle job at a time.

## Build
1. **Theme.** Replace the Afterglow theme with Night shelf tokens, dark and light following the system (existing theme
   override keeps working). No gradients, glows, violet, shadows at rest. Hanken Grotesk 400/600/700 into `res/font/`
   (copy from `design/nightshelf/fonts/`, OFL text beside them) replacing Inter (delete the Inter files and their references).
   Sizes per DESIGN.md; everything usable at 200% font scale; reduced motion = instant.
2. **Shell and Downloads screen.** 56 px top bar: mark + "Elisium" + menu button (History and Settings in the menu sheet).
   Below: link field + inverted "Download" pill, 44 px. Filter chips (All, Downloading, Waiting, Failed, Done; 36 px,
   swipe sideways, selected = 1.5 px `hue` outline, zero shows 0) filtering the list. Rows: 104x59 thumbnail (the item's
   `thumbnail` via the existing image loading, else a `raised` block with the site name, never an icon), title 15/600 two
   lines, meta 13 `faint` from `format_label`/size/"3 of 7 files", 4 px `hue` bar on `track`, percent 24/600 and speed/time
   right, the item `note` under the meta line; states exactly as DESIGN.md "Row states"; failed rows show the reason in
   `negative` and one inverted pill ("Sign in"/"Retry"); done rows "Open · Show in folder". Empty state per desktop.
   Keep every content description, TalkBack text ("N percent") and live region. 44 px minimum targets.
3. **History and Settings** per the approved screens: History grouped by day with search and a site filter, rows with
   "Open / Show in folder / Download again" (Download again = `add(url, force = true)`), the note shown; Settings as grouped
   lists on `surface`: Downloads, Photos and music, Accounts, Appearance, About. "Photos and music" has the two REAL
   settings (photo posts with a song: Photos, song and video / Photos and song only / Photos only; song length: Post's
   snippet / Full song) calling the setters added in 10D. Keep every existing setting.
4. **10E extras.** The title "Looking up the post..." while a photo post, story tray or slideshow is probed; the "Already
   saved" note; a done multi-file post opens its folder.
5. **Owner subfolder.** Make `MediaStoreOutputStore` honour the `subfolder` seam added in 10D (the exact change is in
   `briefs/phase10-d-android-media-engine.result.md`) so posts land in `Download/Elisium/<owner>/`; keep flat behaviour for
   everything else. This is the only edit allowed in `storage/`.
6. **Launcher icon:** the mark (three stacked rounded bars, the last in `hue`) on a black square, adaptive icon XML/vector.

## Tests
JVM tests for the pure bits (filter counts, row text/state mapping, history grouping, settings value mapping, subfolder
path building), a test that the Compose theme tokens equal `design/nightshelf/tokens.json` (read it at test time), and all
existing tests still pass. A Compose UI test only if the project already has Compose test deps.

## Acceptance (paste real output)
```
cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug
python3 design/nightshelf/contrast_check.py
```
(`assembleDebug` may fail offline; if so say exactly why and that the compile of main sources via `:app:compileDebugKotlin`
passed.) No device was available, so list every screen as "not seen on a device". Write the result file even if low on
budget. Keep spend low: read only what you need, run targeted tests while developing, the full run once at the end, and do
not end your turn while Gradle is running.
