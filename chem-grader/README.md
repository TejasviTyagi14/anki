# Reaction Mechanism Grader

Grade multi-step **organic reaction mechanisms** submitted as a directed graph
(structures → steps → structures) against a reference answer. It goes well beyond
string matching: it checks the **structures**, the **transformations between
them**, the **stated mechanism**, optional **arrow-pushing**, and the **overall
pathway** — returning granular, per-node/per-edge feedback with partial credit.

Backend: **Python + RDKit + NetworkX + FastAPI**. Frontend: a self-contained
static prototype (no build step) with a reaction-graph canvas and a
structure-editor integration point.

> This is a pivot of the repo's "handwritten answer → graded against a known
> answer" flashcard prototype (`mockups/handwriting/`). It reuses that project's
> two guiding ideas: a **swappable input recognizer** (there: OCR; here:
> drawing/OCR→SMILES) and **answer-biased grading with toggleable tolerance**
> (there: lenient/normalized/exact; here: tautomer/resonance/stereo flags).

---

## Why SMILES/InChIKey identity (and IUPAC only as a label)

The single most important design decision: **a node's identity is its canonical
SMILES / InChIKey, computed by RDKit — never its IUPAC name.** IUPAC naming is
error-prone, not reliably unique, and not round-trippable, so using it for
grading would corrupt every comparison. IUPAC names are generated **only as a
human-readable label** via a pluggable `NameResolver`, and a naming failure can
**never** block grading.

If you ever want IUPAC to be the source of truth, that is a deliberate,
different (and less sound) design — this codebase intentionally does the opposite.

---

## Architecture

```
             ┌────────────────────────── frontend/ (static, no build) ──────────────────────────┐
             │  graph canvas  ·  structure-editor stub (Ketcher hook)  ·  feedback panel          │
             └───────────────────────────────────────────────┬──────────────────────────────────┘
                                                              │ HTTP (JSON)
┌─────────────────────────────────────────────── src/chemgrader/ ─────────────────────────────────────────────┐
│  api.py            FastAPI endpoints  ─────────────────────────────────────────────────────────────────────  │
│  store.py          in-memory graph store                                                                       │
│  grader.py         Grader — orchestrates the 5 layers → GradeResult                                            │
│  graph_align.py    NetworkX identity-based alignment (alt-route tolerance)                                     │
│  mechanisms.py     MechanismRuleLibrary — SMARTS templates + signature matching                                │
│  transformation.py atom mapping (MCS), conservation checks, bonds formed/broken                                │
│  arrows.py         curved-arrow (electron-flow) consistency / octet checks                                     │
│  structure_service RDKit canonical SMILES · InChIKey · formula · MW · functional groups                        │
│  functional_groups SMARTS functional-group detection                                                          │
│  name_resolver.py  NameResolver protocol + Mock/Null (structure→IUPAC, display only)  ← plug-in point          │
│  structure_input.py StructureInput protocol + Smiles/Molblock/MockOCR (drawing→SMILES) ← plug-in point         │
│  models.py         MoleculeNode · ReactionEdge · ReactionGraph · ArrowOp · ComparisonOptions (pydantic)        │
│  feedback.py       NodeFeedback · EdgeFeedback · GradeResult (structured output)                               │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## The five grading layers

1. **Node correctness** (`grader` + `graph_align` + `structure_service`) — do the
   attempt's structures match the reference by **InChIKey**? Tolerances for
   stereochemistry / tautomers / charge (resonance/protonation) are toggleable.
2. **Transformation validity** (`transformation`) — for each edge, is
   source → product chemically plausible? Builds an **atom map** (via maximum
   common substructure), detects **bonds formed/broken/order-changed**, and runs
   **conservation checks** (element deltas, charge balance).
3. **Mechanism correctness** (`mechanisms`) — does the stated mechanism type +
   reagents match a transformation that could produce the observed change? A
   SMARTS-based **rule library** encodes ~11 MCAT mechanisms with expected change
   signatures and substrate constraints (e.g. *"SN2 on a tertiary carbon"*).
4. **Arrow-pushing** (`arrows`) — if provided, is electron flow consistent with
   the bonds broken/formed and free of valence/octet violations? (partial check)
5. **Path-level grading** (`graph_align` + `grader`) — align the attempt graph to
   the reference, **tolerate valid alternative routes** to the same product, and
   award partial credit per step.

Output is a `GradeResult`: an overall score, a 4-way breakdown
(structures/transformations/mechanisms/pathway), per-node and per-edge verdicts,
and targeted hints.

---

## Quickstart

```bash
cd chem-grader
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements.txt

# run the tests (includes the tricky grading cases)
./.venv/bin/python -m pytest

# run EVERYTHING (API + UI) on a single port
PYTHONPATH=src ./.venv/bin/python -m uvicorn chemgrader.api:app --port 8000
```

Then open **http://localhost:8000/app/** and click **"Load example"**. That's the
whole app — the backend serves the UI from the same origin, so there's no second
server, no CORS, and nothing to configure. Interactive API docs live at
`http://localhost:8000/docs`.

### Molecule builder (skeletal-structure editor)

`/app/builder.html` is a React + SVG skeletal drawing tool (click to add atoms,
drag to bond with 30/120° angle snapping, drag onto an atom to close a ring,
click a bond to change its order, eraser/undo/redo/clear, element picker). It
exposes the drawing as JSON (atoms + bonds) and shows a live SMILES/formula
readout from the backend. It's a single React component in `frontend/builder.jsx`,
precompiled to `frontend/builder.js` (React is self-hosted in `frontend/vendor/`,
no CDN). After editing the component, rebuild with:

```bash
node_modules/.bin/esbuild frontend/builder.jsx --outfile=frontend/builder.js --target=es2018
```

<details><summary>Alternative: serve the UI from a separate static server</summary>

```bash
cd frontend && python3 -m http.server 5173   # open http://localhost:5173
```
Then set the **API** box (top-right) to your backend URL, e.g. `http://localhost:8000`.
CORS is open in dev. The box is blank by default and falls back to the page's own
origin, which is why the single-port mode above needs no configuration.
</details>

---

## Flashcards — draw by hand, graded by a vision model

A second UI at **`/app/flashcards.html`** runs the study loop: it shows a prompt
(the card *front*, e.g. *"SN1 with a tertiary alkyl halide and water"*), you
**draw the answer**, and an OpenAI **vision** model grades the drawing. Two input
modes (toggle at the top):

- **Structured** — a dependency-free SVG structure editor (atoms, bonds,
  wedge/dash stereo, formal charges, reaction arrows, reagent text) that also
  derives SMILES/formula, so the model gets a clean graph *and* the image.
- **Freehand** — a pressure-aware ink canvas (mouse / finger / Apple Pencil).
  Only the rasterized image is sent; the model reads the structure from the
  sketch.

How it works:

- The browser turns the drawing into a PNG snapshot and, in structured mode, a
  machine-readable molecular graph (per-molecule SMILES/formula, atoms, bonds,
  and reactant/product roles, computed client-side in `frontend/chem.js`).
- The image (and graph, if any) is POSTed to `POST /flashcards/grade`. In
  structured mode the server adds a deterministic **RDKit second opinion**
  (canonical-SMILES match against the accepted answer); in freehand mode it
  grades from the image alone. It then calls the vision model with the problem,
  the image, the graph, and the **hidden answer key**. The answer keys live only
  on the server (`src/chemgrader/flashcards.py`) and are never sent to the browser.
- The model grades the chemistry (connectivity, regio-/stereochemistry, charges),
  **solves the problem itself**, and returns a verdict / 0–10 score / what's
  right / what's wrong / explanation / study tip.
- **Hint mode** grades honestly without revealing the product.

### Configure the model (server-side key)

The key is read on the server and never reaches the browser. Two ways to set it:

**Option A — a gitignored `.env` file (recommended; works no matter which shell
launches the server):**

```bash
cd chem-grader
cp .env.example .env          # then open .env and paste your key
```

**Option B — export it in the shell you start the server from** (an explicit
export overrides `.env`):

```bash
export OPENAI_API_KEY=sk-...                        # required
export OPENAI_MODEL=gpt-4o                          # optional (default: gpt-4o)
export OPENAI_BASE_URL=https://api.openai.com/v1    # optional; Azure/gateway base URL
```

Then (re)start the server and open **http://localhost:8000/app/flashcards.html**:

```bash
lsof -ti tcp:8000 | xargs kill -9 2>/dev/null       # free the port if one is already running
PYTHONPATH=src ./.venv/bin/python -m uvicorn chemgrader.api:app --port 8000
```

The `.env` is loaded at startup, so **restart the server after editing it**.
Without a key the grade endpoint returns a clear `503` (the answer key is never
leaked in the process).

---

## API

| Method + path              | Purpose |
| -------------------------- | ------- |
| `POST /reference`          | Store a reference `ReactionGraph` → `{id}` |
| `GET  /graph/{id}`         | Fetch a stored (enriched) graph |
| `POST /grade`              | Grade an attempt vs a reference (`reference` object or `reference_id`) → `GradeResult` |
| `POST /structure/canonical`| SMILES → canonical SMILES, InChIKey, formula, MW, functional groups, name |
| `POST /structure/from-input`| `{source: smiles\|molblock\|ocr, payload}` → SMILES (the StructureInput seam) |
| `GET  /mechanisms`         | List the mechanism rule library |
| `GET  /flashcards`         | List flashcard prompts (fronts only, no answer keys) |
| `POST /flashcards/grade`   | Grade a hand-drawn answer (image + graph) with the vision model |

### Example: grade an attempt

```bash
curl -s -X POST localhost:8000/grade -H 'Content-Type: application/json' -d '{
  "reference": {
    "nodes": [{"id":"a","smiles":"CCBr"},{"id":"b","smiles":"C=C"}],
    "edges": [{"id":"e1","source":"a","target":"b","reagents":["KOtBu"],"mechanism_type":"E2"}]
  },
  "attempt": {
    "nodes": [{"id":"a","smiles":"CCBr"},{"id":"b","smiles":"C=C"}],
    "edges": [{"id":"e1","source":"a","target":"b","reagents":["NaOH"],"mechanism_type":"SN2"}]
  }
}'
# → right product, but mechanism_consistent:false (SN2 can't give an elimination)
```

---

## Data model (serialization)

Everything is pydantic v2, so `.model_dump()` / `.model_validate()` round-trip to
JSON. A `MoleculeNode` needs only `id` + `smiles` on input; identity/property
fields are filled in by `StructureService.enrich`.

```jsonc
{
  "nodes": [
    {"id": "a", "smiles": "CC(C)(C)Br", "label": "optional"},
    {"id": "b", "smiles": "CC(C)(C)O"}
  ],
  "edges": [
    {
      "id": "e1", "source": "a", "target": "b",
      "reagents": ["H2O"], "solvent": "acetone", "conditions": "heat",
      "mechanism_type": "SN1",
      "arrows": [
        {"source": "bond:1-4", "target": "atom:1", "electrons": 2},
        {"source": "lp:5", "target": "atom:1", "electrons": 2}
      ]
    }
  ]
}
```

Arrow endpoints are `atom:i`, `bond:i-j`, or `lp:i` where `i`/`j` are 0-based atom
indices into the **reactant**.

---

## Plug-in points (swap in real models without touching the grader)

### 1. Structure → IUPAC name (display only) — `name_resolver.py`

```python
class MyIUPACModel:
    def to_iupac(self, smiles: str) -> str | None:
        return call_stout_or_api(smiles)  # must never raise; return None on failure

grader = Grader(name_resolver=MyIUPACModel())
```

`MockNameResolver` (a tiny lookup + `"[unnamed <formula>]"` placeholder) is used by
default so tests and the API show a label without any external dependency.

### 2. Drawing / OCR → SMILES — `structure_input.py`

Implement `StructureInput.to_smiles(payload) -> str`. Provided implementations:
`SmilesPassthroughInput`, `MolblockInput` (Ketcher exports molblocks),
`MockOcrStructureInput` (fixture lookup standing in for an image→SMILES model).
The API exposes these at `POST /structure/from-input`.

### 3. Structure editor (Ketcher) — `frontend/`

The "Draw…" button opens a modal that routes text through
`/structure/from-input`. To wire real Ketcher, mount `ketcher-standalone` into
`#editor-slot`, and on accept read `ketcher.getMolfile()` and POST it with
`source: "molblock"`. Nothing else changes.

---

## Mechanism rule library

Seeded with SN1, SN2, E1, E2, electrophilic addition, nucleophilic addition,
nucleophilic acyl substitution, electrophilic aromatic substitution, oxidation,
reduction, and acid–base (proton transfer). Each template carries required
substructure SMARTS, an expected change signature (bonds formed/broken, Δ
unsaturation), soft reagent hints, and substrate constraints. Add one by
appending a `MechanismTemplate` in `mechanisms.py::_default_templates`.

---

## ⚠️ Heuristics that can give false positives / negatives (tune these)

These are the places to calibrate; each is annotated in code too.

- **Atom mapping via MCS** (`transformation.py`) — ambiguous for symmetric
  molecules (first match is taken) and can **under-map** when a single "step"
  changes a lot, lowering `mcs_coverage`. Steps below `min_mcs_coverage` (default
  0.5) are flagged as "possibly more than one step" — a **false-negative** risk
  for legitimately large single steps, and a knob to raise if you want stricter
  step granularity.
- **Conservation / "mass balance"** (`transformation.py`) — a graph edge is
  reactant → product only; reagents and byproducts aren't full species, so we
  **cannot truly mass-balance**. Instead we flag *unexplained* carbon changes
  using a **lexical guess** at whether a reagent can donate carbon
  (`_CARBON_REAGENT_HINTS`). This can **false-positive** (an exotic carbon source
  we don't recognize) or **false-negative** (a reagent string that merely
  contains a "C"). Charge changes are surfaced as warnings, not errors.
- **Mechanism matching is signature-based, not full reaction enumeration**
  (`mechanisms.py`) — an unrelated transformation that happens to share a
  signature (same bonds formed/broken + Δ unsaturation) could be accepted
  (**false positive**). Conversely, `delta_unsaturation` is matched **exactly**,
  so a step that does two things at once may be rejected (**false negative**).
- **Substrate plausibility** (e.g. "SN2 on tertiary", "SN1 on primary") is a
  **coarse steric/carbocation heuristic** — reported as a warning, and it reduces
  but doesn't zero the mechanism score.
- **Reagent matching** is **substring hinting** only — it nudges confidence and
  can misfire on unusual reagent spellings.
- **Arrow-pushing validation is partial** (`arrows.py`) — it checks endpoint
  validity, arrow-count vs. bonds-changed, and a simple neutral-atom octet limit.
  It does **not** do full lone-pair/formal-charge bookkeeping, so subtle
  electron-flow errors can pass (**false negative on catching errors**).
- **Tolerance flags** (`ComparisonOptions`) — `ignore_stereo` strips all
  stereochemistry; `allow_tautomers` uses RDKit's canonical tautomer;
  `ignore_charge` neutralizes (a **coarse** stand-in for resonance/protonation
  tolerance). Turning these on trades strictness for leniency deliberately.

Scoring weights, `pass_threshold`, `min_mcs_coverage`, and `wrong_node_penalty`
all live in `GraderConfig` for tuning.

---

## Tests

`tests/` covers each layer, with `test_grader.py` focused on the tricky cases:
identical attempt, wrong final product, **valid alternative route**, **wrong
mechanism / right product**, **right product / unbalanced step**, and
**stereochemistry mismatch** (strict vs. `ignore_stereo`).

```bash
./.venv/bin/python -m pytest -q
```

## Notes / next steps

- The store is in-memory; swap `GraphStore` for a DB by keeping its 3 methods.
- Consider RXN atom-mapping models (e.g. RXNMapper) to replace MCS mapping for
  higher-confidence transformation analysis.
- The frontend is intentionally minimal (grading correctness was prioritized over
  UI polish); the graph canvas + Ketcher hook are ready to grow.
