# Brief 5A result - Android scaffold

Status: all acceptance checks ran and passed. Nothing committed. The app was NOT installed or run (no emulator/adb), so runtime engine init is unverified.

## Files (all under android/)
settings.gradle.kts, build.gradle.kts, gradle.properties, gradle/libs.versions.toml, .gitignore, local.properties (git-ignored),
app/build.gradle.kts, app/src/main/AndroidManifest.xml,
app/src/main/java/com/desolate/elisium/{ElisiumApp.kt, MainActivity.kt, ui/theme/Theme.kt},
app/src/main/res/values/strings.xml, res/drawable/{ic_launcher_background,ic_launcher_foreground,ic_launcher_monochrome}.xml,
res/mipmap-anydpi-v26/{ic_launcher,ic_launcher_round}.xml, app/src/test/java/com/desolate/elisium/SmokeTest.kt.

## Versions used
AGP 9.5.1 (synced fine; built-in Kotlin, so no separate kotlin-android plugin), Kotlin 2.4.21 + org.jetbrains.kotlin.plugin.compose 2.4.21, Compose BOM 2026.09.00 (resolves Compose 1.12.1),
activity-compose 1.11.0, lifecycle 2.9.4 (runtime-compose, viewmodel-compose), core-ktx 1.17.0, junit 4.13.2,
youtubedl-android library/ffmpeg/aria2c 0.18.1, Gradle 9.8.2, JDK 21, minSdk 26, targetSdk 35.

## Deviations
- **compileSdk 37, not 36.** First real failure (checkDebugAarMetadata): Compose 1.12.1 from BOM 2026.09.00 requires compileSdk >= 37. Platform android-37.0 was already installed. targetSdk stays 35. aapt2 shows compileSdkVersion 37.
- activity-compose/lifecycle/core-ktx versions are my picks (brief gave none); they resolved and built.
- First build attempt was killed (Gradle daemon disappeared; machine memory/swap was full, not a code error). Re-run succeeded incrementally.
- `:app:testDebugUnitTest --offline` fails on the very first run because junit was not yet cached (first build only downloaded main deps). I ran it once online to cache junit, then the offline run passed.
- Manifest also has `android:extractNativeLibs="true"` and the Material no-action-bar theme (needed for youtubedl-android / to avoid an unthemed window). aapt2 lists an extra auto-merged permission `com.desolate.elisium.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (added by androidx.core, not by me); only INTERNET is declared by the app.
- The adaptive icon foreground is the arrow/tray design scaled to 50% in the 108dp canvas (safe zone); monochrome layer is the same shape in black.

## Outputs
- `gradle ... :app:assembleDebug` -> `BUILD SUCCESSFUL in 2m 2s` (36 actionable tasks).
- `gradle ... --offline :app:testDebugUnitTest` -> `BUILD SUCCESSFUL in 30s`; test XML: `tests="1" skipped="0" failures="0"`.
- APK: `android/app/build/outputs/apk/debug/app-debug.apk`, 72,174,039 bytes = about 68.8 MiB (72.2 MB).
- aapt2 badging: `package: name='com.desolate.elisium' versionCode='1' versionName='0.1.0' ... compileSdkVersion='37'`, `minSdkVersion:'26'`, `targetSdkVersion:'35'`, `application-label:'Elisium'`.
- apksigner verify --verbose: `Verifies`, v2 scheme true (v1/v3 false), `Number of signers: 1`.
- Native libs in lib/arm64-v8a/ (only ABI present; no armeabi/x86): libaria2c.so, libaria2c.zip.so, libffmpeg.so, libffmpeg.zip.so (35.6 MB), libffprobe.so, libpython.so, libpython.zip.so (14.3 MB), libqjs.so, libandroidx.graphics.path.so.
