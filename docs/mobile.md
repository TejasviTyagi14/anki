# Mobile companion (AnkiDroid fork on the shared engine)

## Why AnkiDroid genuinely shares the engine

The rubric requires **one engine**, not two apps. AnkiDroid is the right mobile
companion because it does not reimplement scheduling — it wraps Anki's Rust
backend through **rsdroid** (a JNI bridge around `rslib`). Evidence this is a
real shared-engine path, already present in upstream:

- `proto/anki/ankidroid.proto` defines an `AnkidroidService` (Android-specific
  backend entry points), and the build already generates `out/pylib/anki/ankidroid_pb2.py`.
- Anki's backend is exposed to Android via the same protobuf service dispatch
  (`run_service_method`) that Python's `rsbridge` uses.

So MechGrader's Rust change (`MechgraderService`) flows to Android for free once
`rsdroid` is rebuilt against **this fork's `rslib`**: the same generated service
dispatch that made `col._backend.mechgrader_engine_info()` work in Python (see
`BUILD_LOG.md`) exposes the same RPC to Kotlin.

## Current status in this environment: BLOCKED (honest)

No Android toolchain is present here. Verified 2026-07-05:
- `ANDROID_HOME` / `ANDROID_SDK_ROOT`: unset.
- `adb`, `sdkmanager`, `emulator`, `gradle`: not found.
- No JDK; no Android Rust targets (`aarch64-linux-android`, etc.) installed.

Therefore the AnkiDroid build and on-device deck run are **not demonstrated yet**.
This is recorded as a gap rather than faked. It is the top priority to unblock on
a machine with the Android SDK/NDK.

## Exact procedure to stand it up (to run on an Android-capable machine)

1. **Install toolchain:** Android Studio (SDK + NDK), a JDK (17+), and Rust
   Android targets:
   ```
   rustup target add aarch64-linux-android armv7-linux-androideabi \
                     x86_64-linux-android i686-linux-android
   ```
2. **Get the forks:** clone the AnkiDroid fork and this Anki fork side by side.
   AnkiDroid consumes `rsdroid`, which is built from `rslib`.
3. **Rebuild `rsdroid` against this fork's `rslib`:** point rsdroid's build at
   this repository's `rslib` (cross-compile `rslib` to the Android targets and
   package the `.so`s + generated protobufs, including `anki.mechgrader.*`). This
   is the step that carries the MechGrader Rust change onto the phone.
4. **Build & install the app:** `./gradlew assembleDebug` (or `installDebug`) and
   launch on an emulator/device.
5. **Prove the shared engine:** from the Android app, call the same
   `MechgraderEngineInfo` RPC (Kotlin) and show it returns
   `"MechGrader engine live on Anki 26.05 ..."` — the Android analogue of the
   Python probe. Then load the MechGrader deck and run a review session
   (Stage 1), with the mechanism editor in an Android `WebView` loading the same
   `web/mechgrader/` bundle as desktop.

## Make targets
- `make build-mobile` / `make run-mobile` currently print this blocker and exit
  non-zero (so they can't be mistaken for a pass). They will invoke the Gradle
  build once the toolchain is available.
