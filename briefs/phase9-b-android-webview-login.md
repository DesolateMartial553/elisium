# Brief 9B - "Sign in to Instagram" inside the Android app

Read `AGENTS.md`, `core-spec/SPEC.md` ("Sign-in (cookies)"), `briefs/phase8-b-android-instagram-tiktok.result.md`, `briefs/phase9-a-errors-and-keys.result.md`, `design/DESIGN.md`, then under `android/app/src/main/java/com/desolate/elisium/`: `settings/CookieJar.kt`, `settings/CookiesFile.kt`, `ui/settings/SettingsScreen.kt` + `SettingsViewModel.kt`, `ui/ElisiumShell.kt`, `ui/downloads/QueueRows.kt`, and how `DownloadQueue` finds the cookies file (`activeCookiesFile`). Edit only under `android/` and write `briefs/phase9-b-android-webview-login.result.md`. No desktop edits, no commit/push, no emulator/adb, no network in tests, no new dependencies, no new permissions (INTERNET already exists).

## Goal
Today the user must export a `cookies.txt` on a computer and copy it to the phone. Replace that with one tap: a WebView on Instagram's real login page. When login succeeds, capture the session cookies and store them through the existing cookie plumbing. The app never sees or stores the password.

## Build
1. **Pure helpers** in a new `settings/InstagramSession.kt` (JVM-testable, no Android imports):
   - `parseCookieHeader(header: String?): List<Pair<String, String>>`: splits the `name=value; name2=value2` string that `CookieManager.getCookie` returns; ignores blanks and entries without `=`; keeps `=` characters inside values.
   - `hasInstagramSession(header: String?): Boolean`: true only when a `sessionid` cookie with a non-empty value is present.
   - `toNetscape(header: String, nowEpochSeconds: Long): String`: a valid Netscape file: the `# Netscape HTTP Cookie File` header, then one tab-separated 7-field row per cookie: domain `.instagram.com`, include-subdomains `TRUE`, path `/`, secure `TRUE`, expiry `nowEpochSeconds + 31_536_000` (one year; the header carries no expiry), name, value. Tabs/newlines in a name or value must not be able to break the row (drop such cookies). The output must pass `checkCookiesFile` as `Valid(count)`.
2. **Login screen** `ui/settings/InstagramLoginScreen.kt` (Compose + `AndroidView` WebView), full-screen, with a top bar (Back and a short title):
   - Loads `https://www.instagram.com/accounts/login/`. JavaScript and DOM storage on; everything else default. Do not inject any script, do not intercept form fields, do not read the page.
   - Navigation guard (`shouldOverrideUrlLoading`): allow only `https` URLs whose host is `instagram.com`, `facebook.com`, `fbcdn.net` or a subdomain of them (Facebook login redirects); block everything else (no `intent:`/`http:`/other hosts).
   - Detect success by reading `CookieManager.getInstance().getCookie("https://www.instagram.com")` in `onPageFinished` and also on a 1-second poll while the screen is shown; when `hasInstagramSession` is true, build the file with `toNetscape`, call back `onSession(text)` exactly once, then clear the WebView's cookies and web storage (`removeAllCookies`, `WebStorage.deleteAllData`) and `clearCache(true)`, and close the screen. Never log cookie text or the header.
   - Show a short, plain explanation above/below the page before login: "You sign in on Instagram's own page. Elisium never sees your password; it only keeps the session on this phone. If you download a lot, use a spare account." Keep Afterglow styling, TalkBack labels, reduced motion. Destroy the WebView in `onDispose`.
3. **Wire it up.**
   - Settings > Accounts: primary button "Sign in to Instagram" opens the login screen; on `onSession(text)` call `SettingsViewModel.importCookies(text)` (it validates and stores via the existing `CookiesStore`). Status line when stored: "Signed in to Instagram" (keep the cookie count out of the main line). The existing remove action is relabelled "Sign out". The old "Import cookies.txt" document-picker flow stays, moved under a collapsed "Advanced: import cookies.txt" section with its existing help text.
   - A failed item's "Sign in" action (`SIGN_IN_CODES`, `RowAction.SignIn`, `ElisiumShell.kt` `focusAccounts`) now opens the login screen directly instead of only scrolling to Accounts. Keep `focusAccounts` for the Advanced section.
   - Update the Android fix texts in `Errors.kt` that say "Import cookies in Settings > Accounts" / "Import cookies.txt again..." to "Sign in to Instagram in Settings > Accounts" (the login_required, cookies_unreadable and session_expired rows; keep codes). Update the existing tests that assert those strings.
   - Confirm the new cookie file reaches `DownloadQueue` for the next probe/download without an app restart (read how `activeCookiesFile()` works; if it caches, fix it and test it).
4. Strings go in `res/values/strings.xml`. Do not change `allowBackup`/backup rules (cookies stay excluded).

## Tests (JVM, no network)
`InstagramSessionTest`: header parsing (empty, no `=`, `=` inside values, extra spaces), `hasInstagramSession` (missing, empty value, present), `toNetscape` (row shape, expiry, header line, output passes `checkCookiesFile` as `Valid(n)`, hostile name/value with tab/newline dropped), plus the updated `ErrorsTest`/UI tests. Keep all 382 existing tests passing (changed fix-text assertions excepted). Compose UI that needs a real WebView is compile-verified only; say so.

## Acceptance (paste real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:lintDebug
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
```
Zero lint errors; first build may be OOM-killed, retry. List "Needs a real phone" items (login page rendering, 2FA, success detection, cookie reaching yt-dlp, TalkBack). Write the result file even if low on budget.
