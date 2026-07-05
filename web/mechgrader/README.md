# MechGrader — shared web bundle

A **framework-free** (vanilla ES module) bundle for drawing and submitting
organic-chemistry **reaction mechanisms** with **curved-arrow (electron-pushing)**
annotations. It is written **once** and is meant to be embedded unchanged in:

- **Anki's desktop reviewer webview** (Qt `QWebEngineView`, served over HTTP by
  Anki's mediasrv), and
- **an Android WebView** (later), loaded from app assets.

No build step, no framework, no runtime CDN. The only "heavy" pieces (a real
structure editor and real cheminformatics) are **documented seams** you can wire
in later; the bundle is fully usable without them.

---

## Files

| File | What it is | Real / Stubbed |
| --- | --- | --- |
| `mechanism.js` | The `Mechanism` / `Step` data model. `serialize()` / `deserialize()` round-trip EXACTLY the grader's JSON shape. Add/remove step, reactant, product, arrow. Endpoint helpers + validation. No DOM. | **Real** |
| `arrows.js` | The curved-arrow overlay (`ArrowOverlay`) + a pure-geometry anchor layout (`layoutAnchorsLinear`). Click a source, then a target → store `{from,to,kind:"curved"}` → render an SVG **quadratic** arrow. Data first, render second. Structure-agnostic. | **Real** |
| `editor.js` | `MechEditor`: step add/remove UI, per-step reactant/product **SMILES text inputs** (usable with no Ketcher), the `#ketcher-slot` mount seam, the arrow tool + a keyboard-accessible add-arrow control, a read-only prompt pin, and a **Submit** that assembles JSON + dispatches grading. | **Real** (editor); Ketcher mount is a **seam** |
| `rdkit.js` | RDKit-JS (WASM) seam (`loadRDKit`) + `canonicalize` / `productsMatch` / `gradeAgainstReference`, with a **clearly-labeled pure-JS string fallback**. | Fallback **real**; RDKit is a **seam** |
| `index.html` + `app.css` | A standalone page wiring all of the above: prompt pin, step list, arrow tool, Submit that shows the assembled `Mechanism` JSON + a fallback grade, flip-to-reveal reference, and `Space`/`Enter`/`N` shortcuts. | **Real** (runs as-is) |

---

## Run it standalone

ES modules are fetched with CORS, so the page needs an **HTTP origin** — a
`file://` open will fail to load the modules in most browsers. Use any static
server:

```bash
cd web/mechgrader
python3 -m http.server 5178      # then open http://localhost:5178/
```

You can immediately: type reactant SMILES, click atoms/bonds/lone-pairs to push
curved arrows (or use the **From / To → Add curved arrow** control), add/remove
steps and products, and press **Submit** to see the assembled JSON and a fallback
grade. **Space** flips to the reference answer, **N** loads the next card.

> `index.html` intentionally has **no `app.js`** — the ~one screen of page glue
> lives in a single inline `<script type="module">`. The reusable bundle is the
> four `.js` modules.

---

## Data model (must match the grader + the MechCard `ReferenceMechanism`)

```jsonc
{
  "steps": [
    {
      "reactants": ["[OH-:1]", "[CH3:2][Br:3]"],   // atom-mapped SMILES
      "arrows": [
        { "from": "lp:0",     "to": "atom:1", "kind": "curved" },
        { "from": "bond:1-2", "to": "atom:2", "kind": "curved" }
      ],
      "products": ["[CH3:2][OH:1]", "[Br-:3]"]
    }
  ]
}
```

Arrow **endpoints** are `atom:i`, `bond:i-j`, or `lp:i`, where `i`/`j` are
**0-based atom indices** into the step's reactant(s) (matching chem-grader's
README). `serialize()` emits exactly `{from,to,kind}` in that order.

```js
import { Mechanism } from "./mechanism.js";
const m = Mechanism.deserialize(json);   // parse
const step = m.addStep();                // mutate
step.addReactant("[CH3:2][Br:3]");
step.addArrow({ from: "bond:1-2", to: "atom:2" }); // kind defaults to "curved"
const out = m.serialize();               // -> the exact JSON above
```

---

## How the arrow overlay stores vs renders arrows

**Store first (data):** every recorded arrow is just an object
`{ from, to, kind:"curved" }` pushed onto `overlay.arrows` — the single source of
truth. Recording an arrow (by click or by the keyboard control) mutates only that
array and fires `onArrowsChange`. Nothing about pixels is stored.

**Render second (from data + anchors):** `render()` is a pure function of
`(arrows, anchors)`. An **anchor** is `{ endpoint, x, y }` in the overlay's
viewBox space; the structure layer supplies anchors (from the SMILES fallback
layout, or from Ketcher molfile coordinates). For each arrow, `resolve(endpoint)`
turns the token into a point (`bond:i-j` falls back to the midpoint of atoms `i`
and `j`; `lp:i` to an offset from atom `i`), and the renderer draws a
**quadratic Bézier** `M sx sy Q cx cy tx ty` with the control point bowed
perpendicular to the chord. **If an endpoint can't be resolved** (e.g. the
structure has no coordinates yet, or a Ketcher redraw removed an atom), the arrow
**stays in the data** and is simply skipped by the renderer (the overlay shows a
small "N arrows stored (endpoint off-structure)" note). This is what makes the
overlay **work regardless of how the underlying structure is drawn**.

---

## Embedding

The bundle is transport-agnostic. The **only** integration decision is *where the
grade goes*, controlled by `MechEditor`'s submit dispatch:

1. `window.mechgraderGrade(mechanism)` if defined (sync or async) — the host app
   supplies grading (e.g. bridge to Python or a native layer), **else**
2. `POST` the JSON to a configurable `gradeEndpoint`, **else**
3. nothing — the assembled `mechanism` is returned to `onSubmit` for display.

```js
import { MechEditor } from "./editor.js";
const editor = new MechEditor(document.getElementById("host"), {
  prompt: "SN2: hydroxide + bromomethane…",
  gradeEndpoint: "/grade",                 // used only if window.mechgraderGrade is absent
  onSubmit: (mechanism, grade, error) => { /* render */ },
});
```

### (a) Anki desktop reviewer webview

Anki serves web assets over HTTP via mediasrv (e.g.
`http://127.0.0.1:40000/_anki/…`), so `type="module"` imports and (later) WASM
work normally. Drop `web/mechgrader/` where mediasrv can serve it and mount the
editor from the card/page HTML:

```html
<div id="mech-host"></div>
<script type="module">
  import { MechEditor } from "/_anki/…/mechgrader/editor.js";
  // Bridge grading to Python using Anki's pycmd() (see qt/aqt/data/web/js/pycmd.d.ts):
  window.mechgraderGrade = (mechanism) =>
    new Promise((resolve) => {
      // pycmd sends a message to the Python side; wire a handler that runs the
      // real chem-grader and calls back with the GradeResult.
      window.pycmd("mechgrade:" + JSON.stringify(mechanism), resolve);
    });
  new MechEditor(document.getElementById("mech-host"), { prompt: "…" });
</script>
```

On the Python side, handle the `mechgrade:` message in your webview's
`onBridgeCmd`, run the Python grader (the `chem-grader` service), and return the
`GradeResult`. Nothing in the bundle changes.

### (b) Android WebView

Load the same files from app assets. Prefer **`WebViewAssetLoader`** (serves
assets over `https://appassets.androidhost/…`) so ES modules and the RDKit WASM
load without `file://` restrictions:

```kotlin
val assetLoader = WebViewAssetLoader.Builder()
    .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
    .build()
webView.webViewClient = object : WebViewClientCompat() {
    override fun shouldInterceptRequest(view: WebView, req: WebResourceRequest) =
        assetLoader.shouldInterceptRequest(req.url)
}
webView.settings.javaScriptEnabled = true
webView.loadUrl("https://appassets.androidhost/assets/mechgrader/index.html")
```

Bridge grading to native code with a `@JavascriptInterface`:

```kotlin
class GradeBridge { @JavascriptInterface fun grade(json: String): String { /* … */ } }
webView.addJavascriptInterface(GradeBridge(), "MechGraderNative")
```

```js
// in a small page-init script
window.mechgraderGrade = (m) => JSON.parse(window.MechGraderNative.grade(JSON.stringify(m)));
```

(If you must use `file:///android_asset/`, enable
`WebSettings.setAllowFileAccess`/module support carefully; `WebViewAssetLoader`
is the recommended path and avoids module/WASM `file://` pitfalls.)

---

## Seams (how to make the stubs real)

### Ketcher (structure editor) — `#ketcher-slot` in `editor.js`

Without Ketcher, the editor renders a lightweight SMILES-derived depiction into
`#ketcher-slot` and the arrow overlay works over it. To use real Ketcher:

1. **Vendor `ketcher-standalone` offline** (no CDN) into `web/mechgrader/vendor/ketcher/`.
2. Mount it into `#ketcher-slot` per Ketcher's docs, and hide the fallback
   (`editor.structureSvg.style.display = "none"`).
3. On change/accept, keep the data model in sync and feed real coordinates to the
   overlay:
   ```js
   const molfile = await ketcher.getMolfile();  // MDL molfile with 2D coords
   const smiles  = await ketcher.getSmiles();
   step.reactants[0] = smiles;
   editor.setAnchorsFromMolfile(molfile);       // real atom coords -> overlay anchors
   ```
   `setAnchorsFromMolfile()` (and the exported `anchorsFromMolfile()`) map molfile
   atom/bond lines to overlay anchors, so the **same** curved-arrow overlay works
   unchanged over Ketcher's drawing.

### RDKit-JS (canonical SMILES / product match) — `rdkit.js`

1. **Vendor `@rdkit/rdkit` offline**: copy `dist/RDKit_minimal.js` and
   `dist/RDKit_minimal.wasm` into `web/mechgrader/vendor/rdkit/`.
2. Include the loader before the app (`<script src="./vendor/rdkit/RDKit_minimal.js"></script>`),
   which defines `window.initRDKitModule`.
3. `await loadRDKit({ locateFile: f => "./vendor/rdkit/" + f });` at startup.
   After that, `canonicalize()` / `productsMatch()` use real RDKit automatically.

---

## What is REAL vs STUBBED (honest list)

**Real (works right now, no external deps):**

- The `Mechanism`/`Step` data model + `serialize()`/`deserialize()` (exact JSON shape).
- Curved-arrow overlay: pick source → target, store `{from,to,kind:"curved"}`,
  render a quadratic SVG arrow; keyboard-accessible add + per-arrow remove;
  Esc cancels, Delete removes the selected arrow.
- Step add/remove, reactant/product SMILES inputs, prompt pin.
- Submit → assemble JSON → dispatch to `window.mechgraderGrade` / `gradeEndpoint`.
- The standalone page: prompt, steps, arrow tool, Submit + JSON display, flip
  reference, next card, `Space`/`Enter`/`N` shortcuts.

**Stubbed / seams (documented, not shipped):**

- **Ketcher** structure drawing. The offline fallback is a **linear, naive
  depiction**: it lists heavy atoms in SMILES order and only draws bonds between
  *consecutive* atoms — it is **not** a real 2D layout or a SMILES parser (no ring
  closures, branches, or implicit atoms). It exists solely so the arrow tool is
  usable; Ketcher/RDKit provide real atoms, bonds, and coordinates.
- **Real cheminformatics.** The bundled `productsMatch`/`canonicalize` fallback is
  **string-based and explicitly NOT canonicalization** — `"CCO"` and `"OCC"` are
  the same molecule but compare unequal. Every fallback result is labeled
  `canonical:false` / engine `"fallback-string-match (NOT real canonicalization)"`.
- **The full grader.** `gradeAgainstReference` only checks **final-product match**
  (+ light step-count / arrow-presence signals). The real, layered grading
  (structures, transformations, mechanism type, arrow-pushing validity, pathway
  alignment) is the **Python `chem-grader`** service; wire it via
  `window.mechgraderGrade` (desktop) or the native bridge (Android).
- **Atom indexing convention.** Arrow endpoints index heavy atoms across the
  concatenated reactants in written order. This matches the fallback tokenizer;
  with Ketcher/RDKit the indices come from the molecule's real atom ordering.

---

## Accessibility

- Every control is a real `<button>`/`<input>`/`<select>` with a label; toggles/steps
  use radio inputs; icon-only buttons carry `aria-label`s.
- The arrow tool is **not mouse-only**: the **From / To → Add curved arrow**
  `<select>` controls are a full keyboard equivalent to clicking anchors; `Esc`
  cancels a pending pick and `Delete`/`Backspace` removes the selected arrow.
- Visible focus rings (`--focus-ring`), AA-contrast tokens, `aria-live` regions
  for status/grade, and `prefers-reduced-motion` are honored.
