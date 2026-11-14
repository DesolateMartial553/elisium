# Brief 5C result

Implemented by a Sonnet subagent (session cut off before it wrote this file or finished verifying); audited and finished by Claude.

## Delivered
backend/ (YoutubeDlBackend, YtDlpCommands, YtDlpRunner), data/ (Room history), settings/ (DataStore), storage/ (MediaStoreOutputStore, OutputNaming, StorageSpace), service/ (DownloadCoordinator, DownloadService dataSync FGS, NetworkGate Wi-Fi-only, Notifications, QueueSummary, ShareIntake ACTION_SEND), manifest + backup rules (allowBackup=false).

## Fixes Claude made at audit
- YoutubeDlBackend.probe used internal coroutines API (`invokeOnCompletion(onCancelling)`): compile error. Now an `async` + cancellable `await` that destroys the process on cancel.
- DownloadCoordinator: removed no-op `conflate()` on a StateFlow.
- QueueSummary: "Merging 100%" -> percent shown only while state is `downloading` (test expected it).
- MediaStoreOutputStore: lint NewApi errors for MediaStore.Downloads on API 26-28; API 29+ paths now @RequiresApi with an inline SDK_INT check, legacy path unchanged.

## Verified (Claude, 2026-11-14)
`gradle --no-daemon --max-workers=1 :app:testDebugUnitTest :app:lintDebug :app:assembleDebug` -> BUILD SUCCESSFUL, 220 JVM tests, 0 failures/skips, lint clean.

## NOT verified (needs a phone)
MediaStore publish on API 29+ and the legacy API 26-28 path, the foreground service and notifications, Wi-Fi-only gating, share-intent intake, and a real yt-dlp run through youtubedl-android.
