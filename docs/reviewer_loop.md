# The review loop (draw → grade → advance)

How the pieces built in Stage 1 connect into the study flow, what is proven, and
the one part that needs a display to demo.

## The flow
Front (reaction prompt) → Space to flip → draw the mechanism in the embedded
editor → Enter to submit → deterministic grade + itemized breakdown → reference
mechanism shown side-by-side → confirm an FSRS rating (Again/Hard/Good/Easy) and
optionally "keep for review" → next card.

## Components and how they connect
| Piece | Where | Proven by |
| --- | --- | --- |
| MechCard note type (Prompt, ReactionTypeTags, ReferenceMechanism JSON, SourceRef; back template has a `#mechgrader-canvas` mount) | `mechgrader/notetype/mechcard.py` | 5 tests (`make test`) |
| Shared web editor (Ketcher seam + curved-arrow overlay + step mgmt + Submit) | `web/mechgrader/` | `node --check` + 21-assertion smoke test |
| Deterministic grader (RDKit, 5-layer + balance + product-identity) | `mechgrader/grading/` over `chem-grader/` | 62 tests (`make test-grader`) |
| Review pipeline glue (submit → grade → record `mg_pass` → reveal reference) | `mechgrader/reviewer/pipeline.py` | end-to-end test (`make test`) |
| Mastery engine (reads `mg_pass` + FSRS retrievability) | Rust `rslib/src/mechgrader/` | 5 Rust tests |
| Three scores + give-up rule | `mechgrader/scoring/` | 11 tests |

**The data path is proven end-to-end** (`mechgrader/tests/test_reviewer_pipeline.py`):
a MechCard is created → a submission is graded → the per-card `mg_pass` counter is
written to `custom_data` → the **same card is read back by the Rust
`topic_mastery` query**. Model separation is preserved: the pipeline updates only
the mechanism-performance signal (`mg_pass`); the FSRS memory rating is a separate
signal the student confirms (the pipeline only *suggests* one).

## The remaining GUI wiring (documented, not demoable headlessly)
The pipeline is UI-agnostic on purpose. To finish the desktop reviewer:
1. Serve `web/mechgrader/` to the reviewer webview (Anki serves web assets via
   mediasrv) and mount the editor into the MechCard back template's
   `#mechgrader-canvas` (see `web/mechgrader/README.md`).
2. On Submit, the webview calls back via `pycmd("mechgrader:grade:" + json)`; a
   reviewer hook parses it and calls
   `mechgrader.reviewer.pipeline.grade_submission(col, card_id, submitted)`, then
   renders the returned breakdown + `reference` for the side-by-side reveal.
3. Keyboard: Space=flip, Enter=submit, 1–4=FSRS ratings, N=next (Anki-consistent).

This is not wired into `aqt` yet because it can only be verified with a display,
and this environment is headless — shipping untested GUI code would violate the
honesty rule. The pipeline it depends on **is** tested.

## App dependency note (honest)
The desktop deterministic grader uses **Python RDKit**, so the packaged app must
include `rdkit` in its Python environment (add to the app deps), OR grade via the
webview's **RDKit-JS** offline mirror (`web/mechgrader/rdkit.js`). With AI off
(Stage 2), grading + scoring still work via this deterministic path.
