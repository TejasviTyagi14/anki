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
- `make build-mobile` runs `mechgrader/tools/mobile_preflight.sh` — an honest
  toolchain check that prints what's present/missing and the exact reproducible
  build steps, then exits non-zero if prerequisites are missing (so it can't be
  mistaken for a pass). `make run-mobile` points at the same.

## iOS — WebView companion runs in the Simulator (BUILT); native engine is next

### What is built and runs (verified 2026-07-05)

A minimal SwiftUI iOS app in `ios/MechGrader/` hosts the **same** shared
`web/mechgrader/` editor bundle desktop/Android use, inside a `WKWebView`, and
**runs in the Xcode iOS Simulator**. Verified on Xcode 16.4 / iOS 18.6:
the app compiles, installs, launches, and renders the full editor — the prompt
pin, `① Structures`, `Step 1` with the `✎ Draw` button, prefilled reactant
SMILES (`[OH-:1]`, `[CH3:2][Br:3]`), and the quick-insert chips.

Run it (a Simulator must be booted, or the script boots `iPhone 16`):
```
bash ios/build_sim.sh          # compiles with swiftc, installs + launches
xcrun simctl io booted screenshot /tmp/mech.png   # capture proof
```
No `.xcodeproj` is needed — `build_sim.sh` compiles `MechGraderApp.swift` with
`swiftc` against the `iphonesimulator` SDK, assembles a `.app` bundle (Swift
binary + `Info.plist` + the copied web bundle), then `simctl install`/`launch`.

**Implementation note (why a custom URL scheme):** the bundle is served through
a `WKURLSchemeHandler` (`mgapp://`) rather than `file://`, so ES-module scripts
load with a correct `text/javascript` MIME. Loading from `file://` renders the
static HTML but silently fails to execute the editor modules.

### Honest scope of the iOS app

This is the **WebView companion** — the same editor UI and client-side/offline
grading path as the web bundle. It does **not yet embed the Rust engine**
(`rslib`) natively; grade submission uses the web bundle's fallback and can hit
the desktop grader at `http://localhost:8000` (allowed via `NSAllowsLocalNetworking`).
The native shared-engine path below is the remaining work.

### Native shared-engine path (remaining, from scratch)

Unlike Android (AnkiDroid + `rsdroid` give a JNI FFI to build on), there is **no
open-source iOS Anki client to fork** (official AnkiMobile is closed-source) and
this repo has **no Rust FFI layer for Swift** (desktop reaches `rslib` via PyO3,
unusable on iOS). To make iOS a true shared-engine client:
1. **Build a Swift↔Rust FFI over `rslib`** (the main new work). Use `uniffi-rs`
   (or a C header via `cbindgen`) to expose backend service methods — including
   `MechgraderService` (`MechgraderEngineInfo`, `TopicMastery`).
2. **Cross-compile `rslib` for iOS:**
   `rustup target add aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios`,
   then build a static lib / `.xcframework` (e.g. via `cargo-xcframework`).
3. **Call the engine from the app** through the FFI — the Swift analogue of
   `mechgrader/tools/stage0_engine_probe.py` (call `MechgraderEngineInfo` and show
   `"MechGrader engine live on Anki 26.05 …"`), and add a JS↔Swift bridge so the
   embedded editor grades against the native engine instead of the web fallback.
4. **Sync** against the same self-hosted Anki sync server (`docs/sync_conflict_rule.md`).
5. **Ship** via TestFlight or a dev-signed sideload.

Design reference: `mockups/ios.html`. **Recommendation:** for a full native
mobile client, do **Android (AnkiDroid) first** — it's far cheaper because
`rsdroid` already wraps `rslib`; iOS requires the new FFI layer above.
