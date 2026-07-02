# AnkiConcept — iOS app

SwiftUI concept app. The **Write** tab is a **native handwriting flashcard
reviewer** (`HandwritingView.swift`):

- **Capture** — real pen/finger strokes via **PencilKit** (`PKCanvasView`,
  `.anyInput` so finger works too).
- **Recognition** — on-device **Vision** handwriting recognition
  (`VNRecognizeTextRequest`, `.accurate`, revision 3). This is stroke/neural
  recognition in the same class as Apple Notes — far more accurate than image
  OCR (the earlier Tesseract approach).
- **Answer-aware grading** (`AnswerGrader`) — because the expected word is
  known, recognition is biased toward it (`customWords`), we take Vision's
  **N-best candidate list** (`topCandidates`), and the card is correct if the
  answer appears among the candidates (with a small edit-distance fallback).
  Matching the whole candidate list against a known answer is what makes this
  robust to imperfect handwriting without accepting clearly-wrong words.

Recognition is fully **on-device and offline** — no network or API keys.

> The web prototype in `../handwriting/` (browser + Tesseract.js) still exists
> for desktop/browser use, but the iOS app no longer depends on it. The bundled
> `Web/` folder is unused by the current build and can be removed.

## Run on the iOS Simulator

### Option A — Xcode (easiest)
1. `open AnkiConcept.xcodeproj`
2. In the destination menu (top toolbar), pick any iPhone simulator.
3. Press **⌘R**. Open the **Write** tab.

### Option B — command line
```bash
cd mockups/ios-app

# build
xcodebuild -project AnkiConcept.xcodeproj -scheme AnkiConcept \
  -sdk iphonesimulator -configuration Debug \
  -derivedDataPath build/DD -destination 'generic/platform=iOS Simulator' build

# boot a simulator and open the Simulator app
xcrun simctl boot "iPhone 16" 2>/dev/null; open -a Simulator

# install + launch
xcrun simctl install booted build/DD/Build/Products/Debug-iphonesimulator/AnkiConcept.app
xcrun simctl launch booted net.ankiweb.concept.AnkiConcept
```

## Run on your personal iPhone

You need Xcode and a (free) Apple ID.

1. **Add your Apple ID to Xcode**: Xcode ▸ Settings ▸ Accounts ▸ **+** ▸ Apple ID.
2. **Open the project**: `open AnkiConcept.xcodeproj`.
3. **Set signing**: select the *AnkiConcept* target ▸ **Signing & Capabilities**:
   - Check **Automatically manage signing**.
   - **Team**: choose your personal team (your Apple ID).
   - If you get a bundle-ID conflict, change **Bundle Identifier** to something
     unique, e.g. `com.<yourname>.AnkiConcept`.
4. **Enable Developer Mode on the iPhone** (iOS 16+): connect the phone, then on
   the device go to **Settings ▸ Privacy & Security ▸ Developer Mode**, turn it
   on, and restart when prompted.
5. **Pick your device**: plug in the iPhone (tap *Trust* if asked), then select
   it in Xcode's destination menu.
6. **Run**: press **⌘R**. Xcode builds, installs, and launches on the phone.
7. **Trust the developer certificate** (first install only): on the iPhone go to
   **Settings ▸ General ▸ VPN & Device Management**, tap your Apple ID, and
   **Trust**. Re-run from Xcode if needed.
8. Open the **Write** tab and write with your finger or Apple Pencil.

### Notes for free Apple IDs
- Apps signed with a free account **expire after 7 days** — re-run from Xcode to
  refresh.
- You can't install on more than a few devices/apps at once.
- A paid Apple Developer account removes these limits and allows wireless deploy.
