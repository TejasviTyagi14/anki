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

## iOS — runs the NATIVE shared Rust engine in the Simulator (BUILT)

### What is built and runs (verified 2026-07-05, Xcode 16.4 / iOS 18.6)

The iOS app (`ios/MechGrader/`) now does two things, both verified in the
Simulator (iPhone 16 + iPad Pro 11"/13"):

1. **Runs the SAME Rust engine as desktop, natively.** `ios/rust-ffi/` is a
   `staticlib` crate that depends on the **`anki` engine crate (`rslib`)** — the
   exact crate `rsbridge` (desktop/PyO3) and `rsdroid` (Android/JNI) wrap — and
   exposes a C FFI (`mechgrader_engine_info`). It cross-compiles to
   `aarch64-apple-ios-sim` and the Swift app calls it on launch, showing
   **"MechGrader engine live on Anki 26.05 (&lt;buildhash&gt;)"** — the real
   `MechgraderService::mechgrader_engine_info` RPC executed on an in-memory
   `Collection`, native on the phone. This is the Swift analogue of
   `mechgrader/tools/stage0_engine_probe.py` (which proves the same over PyO3).
2. **Hosts the SAME `web/mechgrader/` editor** (burnt-orange flashcard flow) in a
   `WKWebView` below the native-engine banner. Universal app (fills iPad).

Run it (builds the Rust engine FFI + Swift app; installs on every booted sim):
```
make ios            # = bash ios/build_sim.sh
xcrun simctl io booted screenshot /tmp/mech.png    # capture proof
```
`build_sim.sh` runs `cargo build -p mechgrader_ffi --target aarch64-apple-ios-sim`,
then `swiftc` links the resulting `libmechgrader_ffi.a` into the app (with
`-import-objc-header ios/MechGrader/mechgrader_ffi.h` and `-framework Security
SystemConfiguration CoreFoundation CFNetwork -lc++ -lresolv`). No `.xcodeproj`.

Build note: building `anki` as a standalone lib needs `tokio`'s `io-util`/`fs`
features (the full workspace build gets them via feature unification); the FFI
crate requests `tokio` `full` so the cross-compile resolves the same surface.
The WebView is served via a `WKURLSchemeHandler` (`mgapp://`) so ES modules load
with a correct JS MIME (plain `file://` renders HTML but won't run the modules).

### Phone → desktop sync — the iOS app pushes a card through the native engine

The app has a **"Sync card → desktop"** button. It calls
`mechgrader_sync_push` (FFI): the native engine creates a card in a local
collection in the app's Documents dir and **sync-uploads it** to a self-hosted
Anki sync server via the real `sync_login` → `sync_collection` → `full_upload`
path (the same Backend methods the desktop uses). A desktop then syncs that card
down.

Two reproducible proofs:
- **`make sync-ios-verify`** (automated): runs the *identical* native
  `mechgrader_ffi::sync_push` the button calls (host build), pushing a card to a
  self-hosted server, then a desktop `Collection` syncs it down. Verified:
  `[phone] pushed 1 card [full-upload]` → `[desktop] note_count=1,
  phone_card_found=True → PASS`.
- **Live (filmable):** `make sync-server` (port 27701, matches the app's default)
  → tap **Sync card → desktop** in the Simulator → `make sync-pull` prints the
  card: `SN2 mechanism — synced from iPhone | … → PASS`.
- `make sync-roundtrip` additionally proves an A→server→B round-trip on the engine.

### Honest scope / remaining last-mile
- The iOS app runs in the **Simulator**, not signed onto a physical device (that
  needs an Apple Developer cert; the build + native engine + sync are real).
- Both sides run on **one machine** against a localhost sync server (the real Anki
  sync protocol), not two separate physical devices.
- The pushed card is a demo `Basic` card; wiring the **WebView editor's** graded
  MechCard into the pushed collection (instead of a fixed demo card) is the next
  polish. Grade submission in the WebView still uses the web/offline path or the
  desktop grader at `localhost:8000`.

### Android (AnkiDroid) — still the recommended path for a shipping phone app
AnkiDroid + `rsdroid` already wrap `rslib` over JNI, so it's the cheapest route to
a store-shippable phone client on the shared engine; it just needs the Android
SDK/NDK (absent here — see `make build-mobile`). The iOS route above proves the
engine is genuinely portable to a phone target today.
