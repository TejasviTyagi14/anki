#!/usr/bin/env bash
# Build the MechGrader iOS shell (SwiftUI + WKWebView hosting web/mechgrader) and
# run it on a booted iOS Simulator. No .xcodeproj needed — compiles the app with
# swiftc against the iphonesimulator SDK and installs via simctl.
#
# Requires Xcode + an iOS simulator runtime. Usage: bash ios/build_sim.sh
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

BUNDLE_ID="com.mechgrader.demo"
APP="ios/build/MechGrader.app"
SDK="$(xcrun --sdk iphonesimulator --show-sdk-path)"

echo "== assembling $APP =="
rm -rf "$APP"
mkdir -p "$APP/web"
cp web/mechgrader/*.html web/mechgrader/*.css "$APP/web/"
cp web/mechgrader/*.js "$APP/web/"          # .mjs test file is excluded
cp ios/MechGrader/Info.plist "$APP/Info.plist"

echo "== compiling (arm64 iOS simulator) =="
xcrun --sdk iphonesimulator swiftc \
  -target arm64-apple-ios18.0-simulator \
  -sdk "$SDK" \
  -parse-as-library \
  -framework SwiftUI -framework WebKit -framework UIKit \
  -o "$APP/MechGrader" \
  ios/MechGrader/MechGraderApp.swift

# Collect booted simulators (boot iPhone 16 if none).
BOOTED=$(xcrun simctl list devices booted | grep -oE '[0-9A-Fa-f-]{36}')
if [ -z "$BOOTED" ]; then
  xcrun simctl boot "iPhone 16" || true
  open -a Simulator || true
  xcrun simctl bootstatus booted -b || true
  BOOTED=$(xcrun simctl list devices booted | grep -oE '[0-9A-Fa-f-]{36}')
fi

echo "== install + launch on all booted simulators =="
# The app is universal (UIDeviceFamily = iPhone + iPad) so it fills iPad screens
# natively instead of running letterboxed.
for udid in $BOOTED; do
  name=$(xcrun simctl list devices | grep "$udid" | sed -E 's/ *\(.*//' | xargs)
  xcrun simctl terminate "$udid" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl install "$udid" "$APP"
  xcrun simctl launch "$udid" "$BUNDLE_ID" >/dev/null 2>&1 || true
  echo "  launched on $name ($udid)"
done
