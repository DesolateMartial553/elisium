# Brief 9B result - "Sign in to Instagram" inside the Android app

Date: 2026-11-15. Status: done; all three acceptance commands pass (400 tests, 0 lint errors, debug APK built).
Nothing was committed or pushed; no emulator, no adb, no sudo, no network in tests, no new dependency,
no new permission.

## Files changed (all under `android/`)

New
- `app/src/main/java/com/desolate/elisium/settings/InstagramSession.kt` - the pure half (no Android
  imports, only `java.net.URI`): `parseCookieHeader`, `hasInstagramSession`, `toNetscape`, plus
  `loginHostAllowed` for the navigation guard (see judgement calls). Header line is the existing
  `COOKIES_HEADER` constant, so the file is the same one `checkCookiesFile` and yt-dlp read.
- `app/src/main/java/com/desolate/elisium/ui/settings/InstagramLoginScreen.kt` - full-screen
  `AndroidView` WebView on `https://www.instagram.com/accounts/login/`. JavaScript + DOM storage on,
  everything else default. No injected script, no form interception, no page reading. Navigation
  guard in `shouldOverrideUrlLoading`. Success = `CookieManager.getCookie("https://www.instagram.com")`
  contains a non-empty `sessionid`, checked in `onPageFinished` and by a 1 s poll while the screen is
  shown. Exactly once (one `AtomicBoolean`), then `toNetscape` -> `onSession(text)`, then
  `removeAllCookies` + `flush`, `WebStorage.deleteAllData`, `clearCache(true)`, close. Nothing about
  the cookie text or the header is ever logged. WebView detached from its parent and `destroy()`ed in
  `onDispose`. Back button + heading + live-region text, no motion at all (so reduced motion is
  honoured by construction).
- `app/src/test/java/com/desolate/elisium/settings/InstagramSessionTest.kt` - 16 JVM tests.

Edited
- `ui/settings/SettingsScreen.kt` - Accounts: primary "Sign in to Instagram" button (opens the login
  screen), status line "Signed in to Instagram" / "Not signed in." (no count in the main line),
  "Sign out" replaces the old remove action. The cookies.txt picker moved into a collapsed
  `Advanced: import cookies.txt` section (with the existing help text, the existing plurals count and
  the existing rejected-file messages). New `onSignIn` parameter.
- `ui/ElisiumShell.kt` - hosts the login screen over the whole app (`Box`), `signIn` now opens it
  instead of switching to Settings; `focusAccounts` kept for the Advanced section (documented in
  place); a snackbar line confirms the import; the Scaffold's semantics are cleared while the login
  page is up so TalkBack cannot wander into the queue behind it.
- `ui/settings/SettingsViewModel.kt` - `importCookies` now returns whether *this* text was stored
  (the snackbar needs the answer synchronously; a rejected text keeps the previous status, so the
  status alone is not the answer). Still validates and stores through the existing `CookiesStore`.
- `engine/Errors.kt` - fix texts only, codes untouched: `login_required` and `session_expired` and
  `cookies_unreadable` now say "Sign in to Instagram in Settings > Accounts".
- `res/values/strings.xml` - new Accounts and login strings; `settings_accounts_none` is now
  "Not signed in."; the old `settings_accounts_remove*` keys replaced by the sign-out pair.
- `settings/CookieJar.kt` - doc comment only (it no longer describes a picker-only flow).
- Tests updated: `engine/ErrorsTest.kt` (the two changed fix-text assertions + the
  cookies_unreadable fix), `ui/AccountsSettingsTest.kt` (one new test: a captured session is stored
  like a picked file, and a non-file is refused), `engine/DownloadQueueTest.kt` (one new test: a
  cookies file written *after* `setCookiesFile` is used by the next attempt without touching the
  queue).

## Cookie file reaching the queue without an app restart

`ElisiumApp.createCoordinator()` calls `queue.setCookiesFile(cookieJar.file)` once, with the fixed
path `filesDir/cookies/cookies.txt`; `DownloadQueue.activeCookiesFile()` re-checks `isFile` on every
probe and every download (and `takeIf` drops a missing path). So the path is cached, the *existence*
is not: the session the login screen writes is picked up by the next attempt with no restart, and
nothing had to be fixed in `DownloadQueue`. The new test in `DownloadQueueTest` pins that behaviour
(file absent -> no cookies passed; file written -> second item's probe and download both get it).

## Commands run (real output)

```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
> Task :app:testDebugUnitTest
BUILD SUCCESSFUL in 57s
```
Test-results XML totals: `tests=400 failures=0 errors=0 skipped=0` (baseline 382 + 18 new: 16 in
`InstagramSessionTest`, 1 in `AccountsSettingsTest`, 1 in `DownloadQueueTest`). The first run failed
my own new `AccountsSettingsTest` case (my `importCookies` return value answered with the old status
after a rejected import); fixed in `SettingsViewModel` as described above, then green.

```
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
> Task :app:lintDebug
BUILD SUCCESSFUL in 2m 57s
```
`app/build/reports/lint-results-debug.sarif`: 19 issues, 0 errors (same 19 warnings as the 9A
baseline: OldTargetApi, GradleDependency, UseKtx etc.). None in `InstagramSession.kt`,
`InstagramLoginScreen.kt`, `SettingsScreen.kt`, `ElisiumShell.kt` or `Errors.kt`.

```
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
> Task :app:assembleDebug
BUILD SUCCESSFUL in 32s
```
Artefact checked, not just the source: `app/build/outputs/apk/debug/app-debug.apk` (75 MB,
16:20) contains `InstagramLoginScreen` in `classes3.dex`/`classes10.dex`, and `resources.arsc` holds
"Sign in to Instagram", "Signed in to Instagram", "Advanced: import cookies.txt" and the exact
explanation sentence. The merged manifest is unchanged: INTERNET was already there, no new
permission, `allowBackup="false"` and the backup rules are untouched.

## Needs a real phone (could not be checked here)

1. The Instagram login page actually rendering and accepting a login in a WebView (Instagram may
   refuse or show a challenge).
2. Two-factor / "confirm it was you" flows, and the Facebook-login redirect chain (`facebook.com`,
   `fbcdn.net` are allowed, but the real chain is untested).
3. Success detection: that `sessionid` appears in the cookie store on the device at the moment the
   page finishes; the 1 s poll is the fallback.
4. That clearing cookies/storage/cache leaves the app's own state intact (it clears every cookie of
   the WebView's profile, which is what the brief asks for).
5. That the written `cookies.txt` really satisfies yt-dlp for an Instagram story or private post
   (unit-tested only against `checkCookiesFile`).
6. TalkBack: back button, heading, live region, and the modal behaviour while the page is up.
7. Third-party cookies are left at the platform default, as the brief says ("everything else
   default"). If Instagram's embedded login frame fails on a device, enabling
   `setAcceptThirdPartyCookies(webView, true)` is the one-line change - deliberately not made.

## Judgement calls (please read)

- **`loginHostAllowed` lives in `InstagramSession.kt`**, next to the three named helpers. The brief
  names three functions but also demands a navigation guard; keeping the guard pure means it is
  JVM-tested (8 assertions) instead of untested Compose code. No Android import is involved.
- **`importCookies` now returns `Boolean`** instead of `Unit`, so the snackbar can tell the user
  whether the session was stored. Existing callers and tests compile unchanged.
- **`ElisiumShell.kt` has a large diff**: the Scaffold is now inside a `Box` (the login screen is an
  overlay), so its whole body was re-indented by 4 spaces. No logic inside changed apart from
  `signIn`, the overlay and the semantics guard.
- **`focusAccounts`** is kept and passed through, but a failed item's "Sign in" no longer sets it
  (it opens the login screen directly). Nothing in this brief sets it to true any more, so it is
  currently an unused-but-working path for the Advanced section.
- **Copy change beyond the brief**: the Accounts status line when nothing is stored now reads
  "Not signed in." instead of "No cookies imported." (the old line was jargon once the primary
  action became a sign-in).
- `core-spec/SPEC.md` still describes the cookies file/browser as the only sign-in routes; it was
  not in the editable list, so it is unchanged. Worth a follow-up brief.
