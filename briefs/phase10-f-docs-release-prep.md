# Brief 10F + 11E + 12F - docs, SPEC, cleanup, release prep, one small re-bench

Read `AGENTS.md`, `core-spec/SPEC.md`, and every result file in `briefs/` for phases 10, 11 and 12 (`phase10-*.result.md`,
`phase11-*.result.md`, `phase12-*.result.md`), then `HANDOFF.md`. Edit only: `core-spec/SPEC.md`, `README.md`,
`desktop/README.md`, `desktop/ACCESSIBILITY.md`, `android/README*` if present, `HANDOFF.md`, `AGENTS.md`,
`design/` (moves and deletions below), `android/gradle/libs.versions.toml` (remove the unused aria2c line only),
`android/app/build.gradle*` (version bump only), `desktop/pyproject.toml` / `packaging/arch/PKGBUILD` (version bump and
dependency lines only), comments in `android/.../engine/Ports.kt` and `settings/CookieJar.kt` (wording only), tests that read
`design/` paths, and write `briefs/phase10-f-docs-release-prep.result.md`. No new features. No commit/push/tag/release, no
sudo, no network except step 7. `nice` for everything. Keep spend low: read only what you need.

## Do
1. **SPEC.md:** add or update rows for everything that shipped (the 10B-1 result lists the rows it wanted): media routing
   (Instagram `/p/`, `/tv/`, stories, highlights, TikTok `/photo/`), archive keys and the two archives (desktop gallery SQLite,
   Android `media-archive.txt`), new error codes and wording (`gallery_dl_missing`, `story_expired`, `private_account`,
   `no_media` fallback), the "converting" state for the mix, `note`, `files_done`/`files_total`, `thumbnail`/`format_label`,
   the output folder per owner, force re-add ("Download again anyway", "Already saved"), photo/song settings, "Faster
   downloads" and the 429 rail, the "Starting... <reason>" states. Fix the cookie wording: the Android media client reads
   `cookies.txt` in-process only to build request headers and never logs it; the same fix in the `Ports.kt` and `CookieJar`
   comments.
2. **Design folder:** make Night shelf the only design. Move `design/nightshelf/*` up into `design/`, replacing the old
   Afterglow `DESIGN.md`, `tokens.json`, `contrast_check.py`; delete the old Afterglow files and any pycache. Update EVERY
   reference (grep for `nightshelf`, `design/tokens.json`, `design/DESIGN.md`, `design/nightshelf`) in code, tests (desktop
   and Android `TokensTest`), docs, AGENTS.md (the Visual design section loses the "Afterglow stays until" sentence), and
   the DESIGN.md header. `python3 design/contrast_check.py` must print ALL PASS afterwards, and the token tests must pass.
3. **README.md:** describe what the app does now (video, photo posts, carousels, stories, TikTok slideshows, songs and the
   photos+song video, Faster downloads), the install notes (`gallery-dl` for photo posts on desktop, `ffmpeg`), the design in
   one line, and use the regenerated `docs/screenshots/` (desktop) with the day/night pairs; no Android screenshots (none
   exist: say "Android screenshots come after a device test" in HANDOFF, not in the README). Remove every Inter/Afterglow
   mention. No claims that were not verified: photo/song support on real Instagram/TikTok is "built and tested on fixtures;
   a live check is pending" in HANDOFF, and the README says what works without overclaiming.
4. **Android leftovers:** remove the unused `youtubedl-aria2c` line from `libs.versions.toml`; bump `versionCode` 5 -> 6 and
   the matching `versionName`; bump the desktop/PKGBUILD version to match the app's next minor (v0.6.0). Do NOT tag.
5. **HANDOFF.md:** a short "State on <date>" section at the top: what shipped, what is unverified (live Instagram/TikTok,
   every Android screen on a device, locks, subfolder writes), what needs the owner (links, phone test, yes to push/release),
   and the exact release checklist (changelog, tag, push, GitHub Release with the APK) marked NOT DONE.
6. **Verification (once each, in this order, one at a time):**
   `cd desktop && QT_QPA_PLATFORMTHEME= nice python3 -m pytest -q` (7-15 min; do not end your turn while it runs),
   `python3 design/contrast_check.py`,
   `cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug`.
   Paste the final line of each.
7. **12F small re-bench (network OK, once):** run `python3 tools/bench.py --rounds 2 --configs base,once <the same short public
   clip URL used in briefs/phase12-a-bench.result.md>` and append the before/after table plus one honest sentence to
   HANDOFF.md and the result file. If the clip is unavailable, say so and skip: do not substitute private or signed-in links.

## Output
Write the result file even if low on budget, with the three verification lines pasted verbatim.
