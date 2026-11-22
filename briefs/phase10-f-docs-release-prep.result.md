# Brief 10F + 11E + 12F result - docs, design folder, release prep, re-bench

Implemented by a Sonnet subagent, 2026-11-22. Nothing committed, pushed or tagged. No sudo, no rm -rf.

## Verification (final lines, verbatim)
```
cd desktop && QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q
981 passed, 2 skipped in 864.52s (0:14:24)   (EXIT 0)

python3 design/contrast_check.py
light     focus on surface   5.64 (need 3.0) PASS
ALL PASS

cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug
BUILD SUCCESSFUL in 8m 10s
45 actionable tasks: 45 executed        (EXIT 0; test XML totals: 640 tests, 0 failures, 0 errors, 0 skipped; app-debug.apk 69,046,649 bytes)
```

## 12F re-bench
`tools/bench.py --rounds 2 --configs base,once 'https://www.youtube.com/watch?v=jNQXAC9IVRw'` (the short clip from 12A)

| URL | config | start s | (probe s) | transfer s | post s | total s | MB | MB/s | failures |
|---|---|---|---|---|---|---|---|---|---|
| https://www.youtube.com/watch?v=jNQXAC9IVRw | base | 9.4 | 5.0 | 0.4 | 0.3 | 10.0 | 0.5 | 1.32 | 1 |
| https://www.youtube.com/watch?v=jNQXAC9IVRw | once | 5.6 | 4.3 | 0.4 | 0.3 | 6.4 | 0.5 | 1.36 | 0 |

12A had base 13.3 s / once 7.9 s. Extract once again saves about 3.6 s of a ~10 s run on a short clip. Caveat: one base round failed with `HTTP Error 403` on the media URL, so the base median is from one run. Same table appended to HANDOFF.md.

## What changed
- **design/**: Night shelf is the only design. `design/DESIGN.md`, `tokens.json`, `contrast_check.py`, `fonts/` (moved up from `design/nightshelf/`); old Afterglow files, both `__pycache__` dirs and the empty `nightshelf/` folder deleted. DESIGN.md header and the "Inter is no longer the typeface" line rewritten; "Afterglow" removed from its Banned heading.
- **References updated** (grep for `nightshelf` now finds nothing outside briefs/): `desktop/tests/test_theme.py` (path + two test names: `test_tokens_equal_design_tokens_json`, `test_design_contrast_check_prints_all_pass`), `desktop/elisium_downloader/ui/theme.py` (docstring), `android/.../ui/theme/TokensTest.kt` (path + messages), `Shape.kt` and `Color.kt` (comment paths only), `design/contrast_check.py` (docstring), `AGENTS.md` (Visual design section rewritten, "Afterglow stays until" sentence gone).
- **core-spec/SPEC.md**: converting stage for the mix; the two media archives and the `<id>_mix` marker; force re-add / "Already saved"; per-owner output folders; cookie wording (Android media client reads cookies.txt in-process only to build headers, never logs it); new "Photo posts..." section (routing table, files_done/total, thumbnail, format_label, note, song + photos video rules and notes, photo/song settings, new error-code table); new "Faster downloads" section (Auto/Off, native audio, 429 rail, smoothed ETA, "Starting... <reason>").
- **Cookie comments**: `Ports.kt` and `CookieJar.kt` wording only.
- **README.md**: rewritten feature list (video, photo posts, carousels, stories, slideshows, songs + photos video, Faster downloads, Night shelf in one line), `gallery-dl` + `ffmpeg` install notes, per-owner folders, day/night screenshot pairs for queue, history, settings, choose-quality, playlist (all files exist in docs/screenshots/), no Inter/Afterglow mention, "built and tested on sample data, not yet checked on live Instagram/TikTok" stated plainly, no Android screenshots.
- **desktop/ACCESSIBILITY.md**: contrast bullet now Night shelf + contrast_check, Reduce motion setting location, one new "not tested" bullet for photo-post rows. (`desktop/README.md` and `android/README*` do not exist; nothing created.)
- **Versions**: Android `versionCode` 5 -> 6, `versionName` 0.5.0 -> 0.6.0; `desktop/pyproject.toml` and `PKGBUILD` (`pkgver` and the hard-coded prefix in `pkgver()`) 0.1.0 -> 0.6.0. No tag.
- **android/gradle/libs.versions.toml**: `youtubedl-aria2c` line removed (nothing referenced it; build passed).
- **HANDOFF.md**: "State on 2026-11-22" section at the top (shipped, unverified, owner needs, 7-step release checklist all marked NOT DONE) plus the re-bench table.

## Left for the owner / not done
- `desktop/elisium_downloader/__init__.py` still has `__version__ = "0.1.0"` (not in this brief's edit list); `elisium --version` prints 0.1.0 until bumped. Listed in the HANDOFF checklist.
- `android/.../settings/SettingsRules.kt` line 9 comment still says "Afterglow theme" (file not in the edit list).
- Release (changelog, tag, push, GitHub Release with the APK): NOT DONE, awaits owner's yes.
