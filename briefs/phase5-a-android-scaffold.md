# Brief 5A - Android project scaffold that builds a real APK

Goal: `android/` is a Gradle project for the Android app **Elisium** that compiles to an installable debug APK showing one Compose screen with the bundled yt-dlp version. No download features yet. Everything later (5B-5E) builds on this, so versions and structure matter.

Read `AGENTS.md` and `core-spec/SPEC.md` first (the spec is the source of truth for later briefs; this brief only needs the app name and package id).

## Fixed decisions
- App name (launcher label): **Elisium**. Package / applicationId / namespace: **`com.desolate.elisium`**.
- Kotlin + Jetpack Compose + Material 3 (dynamic colour where available), single `app` module, `minSdk 26`, `compileSdk 36`, `targetSdk 35`. Portrait and landscape both fine.
- Engine library: `io.github.junkfood02.youtubedl-android` **0.18.1**: modules `library`, `ffmpeg`, `aria2c` (Maven Central). It bundles Python + yt-dlp + ffmpeg and can update yt-dlp at runtime.
- Use the Gradle **version catalog** (`gradle/libs.versions.toml`). Use stable versions only (no alpha/beta/RC): AGP **9.5.1** (if it fails to sync, use the newest stable that works and say so), Kotlin **2.4.21** with the `org.jetbrains.kotlin.plugin.compose` plugin, Compose BOM **2026.09.00**, plus `androidx.activity:activity-compose`, `androidx.lifecycle:lifecycle-runtime-compose` and `lifecycle-viewmodel-compose`, `androidx.core:core-ktx`. Add Room, WorkManager, coroutines, DataStore and test libs NOW to the catalog only if you need them to compile; otherwise leave them for later briefs.
- Use the system `gradle` (9.8.2), **no wrapper required**. Java: AGP does not support the default JDK 27, so always run with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk`.
- ABI: for debug builds package **only `arm64-v8a`** (`ndk { abiFilters += "arm64-v8a" }`) to keep the APK small; release splitting comes later.
- Machine limits (2 cores, ~1 GB free RAM, no emulator, no adb): see `AGENTS.md`. `gradle.properties` must contain `org.gradle.jvmargs=-Xmx1g`, `org.gradle.workers.max=1`, `org.gradle.parallel=false`, `kotlin.daemon.jvmargs=-Xmx768m`, `kotlin.compiler.execution.strategy=in-process`, `android.useAndroidX=true`, `org.gradle.caching=false`. Run Gradle with `nice` and `--no-daemon`.
- The FIRST build must download dependencies from Maven Central / Google (one-time, several hundred MB because of the bundled Python and ffmpeg). That network use is allowed for dependency resolution only. Later builds should work with `--offline`.

## Create (inside `android/`)
- `settings.gradle.kts` (repos: `google()` limited to the Android groups, `mavenCentral()`, project name `Elisium`), root `build.gradle.kts`, `gradle.properties`, `gradle/libs.versions.toml`, `.gitignore` (build dirs, `.gradle/`, `local.properties`, `*.jks`, `*.keystore`), and a `local.properties` with `sdk.dir=/home/desolate/Android/Sdk` (it is git-ignored; do not commit it).
- `app/build.gradle.kts` (namespace and applicationId as above, `versionCode 1`, `versionName "0.1.0"`, `packaging { jniLibs { useLegacyPackaging = true } }` as youtubedl-android requires, resource shrinking off for debug, Compose enabled).
- `app/src/main/AndroidManifest.xml`: `INTERNET` permission, an `Application` class, one launcher `MainActivity`, label `@string/app_name`. Do NOT add storage or foreground-service permissions yet.
- `app/src/main/java/com/desolate/elisium/ElisiumApp.kt`: `Application` that initialises `YoutubeDL`, `FFmpeg` and `Aria2c` on a background coroutine (not the main thread) and exposes the result (ready / failed with message) through a `StateFlow`.
- `MainActivity.kt` + `ui/theme/Theme.kt`: Material 3 theme with dynamic colour on Android 12+ and a fixed dark/light fallback; one screen titled **Elisium** that shows "Starting engine..." then "Engine ready - yt-dlp <version>" (from `YoutubeDL.version(context)`) or the plain error message. Accessibility from the start: text uses `MaterialTheme.typography`, the status text has a `liveRegion = Polite` semantic, no colour-only meaning.
- `app/src/main/res`: `values/strings.xml` (`app_name` = Elisium), an adaptive launcher icon built as vector drawables (foreground: a down-arrow into a tray line, colour `#C9A7F2`; background `#1E1A2E`; also a monochrome layer for themed icons), `mipmap-anydpi-v26/ic_launcher.xml` and `ic_launcher_round.xml`. The same design as `desktop/packaging/elisium.svg`.
- `app/src/test/java/.../SmokeTest.kt`: one trivial JVM unit test so `:app:testDebugUnitTest` has something to run (this proves the test setup for later briefs).

## Acceptance (run all, paste the real output)
```
cd android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
nice gradle --no-daemon --max-workers=1 -Dorg.gradle.jvmargs=-Xmx1g :app:assembleDebug
nice gradle --no-daemon --max-workers=1 --offline :app:testDebugUnitTest
```
Then verify the APK (`app/build/outputs/apk/debug/*.apk`) WITHOUT installing it:
- `~/Android/Sdk/build-tools/36.0.0/aapt2 dump badging <apk> | head` shows package `com.desolate.elisium`, label `Elisium`, minSdk 26.
- `~/Android/Sdk/build-tools/36.0.0/apksigner verify --verbose <apk>` passes (debug-signed).
- `unzip -l <apk>` lists `lib/arm64-v8a/` native libraries from youtubedl-android and report the APK size in MB.
If the build runs out of memory, lower parallelism further or close other work; do not raise memory settings above the values above without saying so.

## Do not
Install anything with `sudo`, start an emulator, use `adb`, add dependencies beyond those named, request permissions beyond `INTERNET`, add download logic, commit, or push. Write `briefs/phase5-a-android-scaffold.result.md` (files, exact versions actually used, exact command output, APK size, anything that deviated from this brief and why).
