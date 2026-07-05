#!/usr/bin/env bash
# MechGrader mobile (AnkiDroid fork) build preflight.
#
# The Android app is NOT buildable without a full Android toolchain. This script
# honestly checks what's present, and prints the EXACT, reproducible commands to
# build the AnkiDroid fork with rsdroid rebuilt against THIS repo's rslib (so the
# MechGrader Rust change ships to the phone). It never pretends to have built an
# APK. Exit 0 = toolchain ready to build; 2 = prerequisites missing.
#
# Usage:  bash mechgrader/tools/mobile_preflight.sh

miss=0
say() { printf '  %-24s %s\n' "$1" "$2"; }
check() { # name  test-command
  if eval "$2" >/dev/null 2>&1; then say "$1" "PRESENT"; else say "$1" "MISSING"; miss=$((miss+1)); fi
}

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"

echo "== MechGrader mobile build preflight =="
echo "Prerequisites:"
check "JDK 17+ (javac)"          "javac -version 2>&1 | grep -Eq '1[7-9]|2[0-9]'"
check "Android SDK (ANDROID_HOME)" "test -n \"$SDK\" && test -d \"$SDK\""
check "sdkmanager"               "command -v sdkmanager"
check "Android NDK"              "test -n \"${ANDROID_NDK_HOME:-}\" || ls \"${SDK:-/nonexistent}\"/ndk >/dev/null 2>&1"
check "rustup"                   "command -v rustup"
check "rust android targets"     "rustup target list --installed 2>/dev/null | grep -q aarch64-linux-android"
check "cargo-ndk"                "command -v cargo-ndk"
check "AnkiDroid fork checkout"  "test -d ../Anki-Android"

echo ""
if [ "$miss" -eq 0 ]; then
  echo "Toolchain looks READY. Build steps:"
else
  echo "$miss prerequisite(s) MISSING — install them, then run the build steps below."
fi

cat <<'STEPS'

Reproducible build (run on a machine with the Android toolchain):

  1) Install: Android Studio (SDK + NDK), a JDK 17+, and Rust Android targets:
       rustup target add aarch64-linux-android armv7-linux-androideabi \
                         x86_64-linux-android i686-linux-android
       cargo install cargo-ndk

  2) Clone the AnkiDroid fork next to this repo:
       git clone <your AnkiDroid fork> ../Anki-Android

  3) Rebuild rsdroid against THIS repo's rslib (carries the MechgraderService
     change onto Android), then build the app:
       # point rsdroid's build at this checkout's rslib, cross-compile, then:
       cd ../Anki-Android && ./gradlew assembleDebug     # or installDebug

  4) Prove the shared engine on-device: call MechgraderEngineInfo / TopicMastery
     from Kotlin (Android analogue of mechgrader/tools/stage0_engine_probe.py),
     then load the MechGrader deck with the web editor in the Android WebView.

See docs/mobile.md for the full procedure and rationale.
STEPS

[ "$miss" -eq 0 ] && exit 0 || exit 2
