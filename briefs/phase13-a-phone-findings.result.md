# Phase 13-A: phone findings (0.6.0-rc1) - result

## Files changed
- android/app/src/main/java/com/desolate/elisium/ui/settings/InstagramLoginScreen.kt (bug 1)
- android/app/src/main/java/com/desolate/elisium/ui/settings/LoginLoadError.kt (new, pure helpers for bug 1)
- android/app/src/main/res/values/strings.xml (4 strings: loading, load failed, retry, webview name)
- android/app/src/main/java/com/desolate/elisium/engine/Errors.kt (sanitiser, withCause, wider Instagram login wording)
- android/app/src/main/java/com/desolate/elisium/engine/DownloadQueue.kt (catch-alls keep the cause, unknown falls through to the media engine)
- android/app/src/main/java/com/desolate/elisium/media/MediaHttp.kt (401 without WWW-Authenticate no longer an IOException)
- tests: engine/ErrorCauseTest.kt (new, 9 tests), ui/settings/LoginLoadErrorTest.kt (new, 3 tests)

## Bug 1: blank Instagram sign-in box
Root cause NOT provable without a device. Defensive fixes, all in the screen:
- WebView gets an opaque white background (`setBackgroundColor(WHITE)`) and darkening off (API 33+: `isAlgorithmicDarkeningAllowed = false`; API 29-32: `forceDark = FORCE_DARK_OFF`). No androidx.webkit dependency exists, so WebSettingsCompat is not used.
- Removed `.clip(MaterialTheme.shapes.medium)` from the WebView: a rounded clip forces an off-screen layer, a known way for a Compose-hosted WebView to render blank on some devices. The box is now rectangular. (Suspect, not confirmed.)
- Visible "Loading..." line until onPageFinished (live region).
- `onReceivedError` (main frame only) and `onReceivedHttpError` (main frame, status >= 400) show "Instagram's sign-in page did not load (<reason>). Check your connection." with a Retry button that calls `loadUrl(LOGIN_URL)` (live region, assertive). Reasons come from the pure `loginErrorReason` / `loginHttpReason` (JVM-tested, description sanitised and cut to 60 chars).
- Unchanged: `loginHostAllowed` navigation guard, cookie poll/hand-over, `clearSignIn`; nothing logs cookies or headers. WebView has a contentDescription ("Instagram sign-in page"); Back and heading semantics kept.
- Could NOT verify without a device: that the page now paints, that the dark-mode settings or removing the clip is what fixed it, that Instagram's login page loads in this WebView at all (it may also be bot-walled by Instagram; if so the new error message or an HTTP 4xx message will now say so).

## Bug 2: "Download failed. See Details" on unsigned /p/ links
Code evidence (what I could establish by reading; no device log exists):
- The media path itself is fine for an unsigned link: `routeFor` gives YTDLP_THEN_MEDIA, `HttpMediaFetcher.igHeaders` tolerates a null cookies file (`cookieHeader`/`cookieValue` return null), 401/403 map to `MediaFailure.LOGIN_REQUIRED`, and `mediaErrorInfo` maps that to `login_required`. The new tests drive exactly this chain (real `HttpMediaFetcher` over a fake transport answering 401) and it ends `login_required`.
- The media engine was only ever reached from `attempt()` when yt-dlp's error mapped to code `no_media` (`error.code == "no_media"`). Any other yt-dlp outcome on a photo post never got there: an unmatched yt-dlp message falls to `FALLBACK` in `explain()` (code `unknown`), and a probe exception that is not a `ProbeFailure` hit the `catch (_: Exception) { error = UNKNOWN }`. Both end as the generic "Download failed. See Details" with the real text discarded. The on-phone yt-dlp therefore must have produced a message not in the table (the desktop-tested text, "There is no video in this post", IS mapped; yt-dlp's other anonymous-Instagram wording, e.g. "The webpage request was redirected to the login page. You have exceeded the rate-limit for accessing posts anonymously", was not). That exact message is my best candidate but is unconfirmed: the swallowed text is gone, which is what (b) fixes for next time.
- Fixes: (1) `attempt()` now also falls through to the media engine when the yt-dlp error is `unknown` on a YTDLP_THEN_MEDIA link (photo posts, single stories), so the engine, not yt-dlp's wording, decides and an unsigned post ends `login_required`; (2) the table gets login wording for "redirected to the login page", "rate-limit for accessing posts anonymously", "only available for registered users", "rate-limit reached or login required"; (3) `UrlConnectionTransport.get` turns Android's `IOException: No authentication challenges found` (thrown for a 401 with no WWW-Authenticate header, which is what a signed-out Instagram sends) into a normal HTTP 401 instead of a "Network problem". (3) is a known Android behaviour but unproven here; compile-verified only.
- (b) Every catch-all (work(), the yt-dlp probe, runMediaAttempt, downloadOnce) now keeps the cause. There is no separate Details screen on Android: the row shows `message + fix`, so the unknown error keeps code `unknown` and message "Download failed." and its fix line becomes `See Details: <ExceptionClass>: <message>` (sanitised, whole cause <= 200 chars; Cookie/Authorization/Set-Cookie header text, sessionid/csrftoken/etc. `name=value` pairs, Netscape cookie rows, Bearer tokens and 32+ char opaque tokens are replaced with `[removed]`). Unmatched yt-dlp errors (probe and download) carry the last log line the same way. History still stores only code and message, so the cause shows for the live row, not after an app restart.
- (c) Tests in ErrorCauseTest: unsigned /p/ with an engine that throws LOGIN_REQUIRED on missing cookies -> login_required (both photo URLs); real fetcher over a 401 transport -> login_required with no Cookie header sent; non-ProbeFailure probe crash and unnamed yt-dlp message both reach the engine -> login_required; "redirected to the login page" -> login_required; a thrown exception -> code unknown, message "Download failed.", fix contains class and message and no cookie text; unmatched yt-dlp log and a story-link engine crash keep their cause; sanitiser cases and truncation.

## Acceptance
Command: `cd /home/desolate/Work-Projects/elisium-downloader/android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk nice gradle --offline --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:testDebugUnitTest :app:assembleDebug`

Final run output (tail):
```
BUILD SUCCESSFUL in 1m 34s
45 actionable tasks: 11 executed, 34 up-to-date
```
Tests (from build/test-results XML): 653 tests, 0 failures, 0 errors. (An earlier run of the same command failed once on one new sanitiser test, fixed by redacting Netscape tab rows, then re-run green.)

## Not done / risks
- No device: WebView behaviour and the true on-phone yt-dlp message are unverified.
- Falling through on `unknown` also applies to /p/ video posts where yt-dlp failed oddly; the media engine then tries the Instagram API once (no retry counted).
