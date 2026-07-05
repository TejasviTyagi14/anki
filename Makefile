# MechGrader — top-level task runner.
#
# MechGrader is a fork of Anki (spaced-repetition engine) that adds an
# organic-chemistry mechanism study loop with honest, traceable grading and a
# mastery-aware Rust review pipeline. This Makefile is the single entry point
# the grading rubric expects. It wraps Anki's `just` recipes for the shared
# engine build and adds the MechGrader-specific eval/bench/leakage/gold/sync
# targets. Run `make help` for the list.
#
# Targets that are not yet implemented in the current stage exit non-zero with a
# clear message on purpose — a placeholder must never look like a passing check.

SHELL := /bin/bash

# The Anki fork vendors its own Python + libs under out/. Use them so the
# MechGrader scripts run against the exact engine build the app uses.
# out/pylib -> the built `anki` package; `.` -> the `mechgrader` package.
PYENV := out/pyenv/bin/python
PY    := PYTHONPATH=out/pylib:. $(PYENV)

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "MechGrader make targets"
	@echo "  make build         Build the desktop app (Anki fork: Rust + Python + web)"
	@echo "  make run-desktop   Build & launch the desktop app (needs a display)"
	@echo "  make build-mobile  Build the AnkiDroid fork w/ rsdroid rebuilt on this rslib  [needs Android SDK/NDK — see docs/mobile.md]"
	@echo "  make run-mobile    Install & launch the Android build on a device/emulator     [needs Android SDK/NDK — see docs/mobile.md]"
	@echo "  make test          Run the MechGrader Rust + Python engine tests"
	@echo "  make test-anki     Run the full upstream Anki test suite (cargo + pytest + vitest)"
	@echo "  make stage0-proof  Re-run the Stage 0 engine-liveness proof (Rust test + rsbridge probe)"
	@echo "  make eval          AI grader held-out eval + baseline comparison   [Stage 2]"
	@echo "  make bench         50k-card p50/p95/worst-case benchmarks           [Stage 3]"
	@echo "  make leakage       Near-duplicate / test-set leakage scan          [Stage 3]"
	@echo "  make gold          Build / refresh the held-out gold sets          [Stage 2]"
	@echo "  make sync-server   Start a self-hosted Anki sync server            [Stage 2]"

# ----------------------------------------------------------------------------
# Desktop (shared engine) — real today
# ----------------------------------------------------------------------------

.PHONY: build
build:
	just build

.PHONY: run-desktop
run-desktop:
	just run

# Dev servers for the mechanism editor + the real RDKit grader.
# Each CLEARS ITS PORT FIRST (so re-hosting never hits "address in use").
# Run `make grader` in one terminal and `make editor` in another, then open
# http://localhost:5178 — the editor's Submit POSTs to the grader on :8000.
.PHONY: grader
grader:
	@bash -c 'p=$$(lsof -ti tcp:8000); [ -n "$$p" ] && kill -9 $$p || true'
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m uvicorn chemgrader.api:app --port 8000

.PHONY: editor
editor:
	@bash -c 'p=$$(lsof -ti tcp:5178); [ -n "$$p" ] && kill -9 $$p || true'
	cd web/mechgrader && python3 -m http.server 5178

.PHONY: test-anki
test-anki:
	just test

# MechGrader tests that run against the vendored engine (no RDKit needed).
.PHONY: test
test:
	cargo test -p anki --lib mechgrader
	$(PY) mechgrader/tools/stage0_engine_probe.py
	$(PY) mechgrader/tests/test_topic_mastery.py
	$(PY) mechgrader/tests/test_scoring.py
	$(PY) mechgrader/tests/test_mechcard_notetype.py
	$(PY) mechgrader/tests/test_reviewer_pipeline.py
	$(PY) mechgrader/tests/test_ai_grader.py
	$(PY) mechgrader/tests/test_source_validator.py
	$(PY) mechgrader/tests/test_sync_conflict.py
	$(PY) mechgrader/tests/test_cardgen_check.py
	$(PY) mechgrader/tests/test_eval.py
	$(PY) mechgrader/tests/test_calibration.py
	@echo ">> For the RDKit grader suite + the baseline eval, run: make test-grader eval"

# Deterministic grader suite (needs RDKit in chem-grader/.venv). One-time setup:
#   cd chem-grader && python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
.PHONY: test-grader
test-grader:
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m pytest \
	    mechgrader/tests/test_deterministic_grader.py mechgrader/tests/test_leakage.py chem-grader/tests -q

# Stage 0 gate proof, runnable on its own.
.PHONY: stage0-proof
stage0-proof:
	cargo test -p anki --lib mechgrader
	$(PY) mechgrader/tools/stage0_engine_probe.py

# Stage 1 proof: real Rust change + the review loop end-to-end.
.PHONY: stage1-proof
stage1-proof:
	cargo test -p anki --lib mechgrader
	$(PY) mechgrader/tests/test_topic_mastery.py
	$(PY) mechgrader/tests/test_reviewer_pipeline.py

# ----------------------------------------------------------------------------
# Mobile (AnkiDroid fork on the shared engine) — see docs/mobile.md
# ----------------------------------------------------------------------------

.PHONY: build-mobile
build-mobile:
	bash mechgrader/tools/mobile_preflight.sh

.PHONY: run-mobile
run-mobile:
	@echo "[MechGrader] Install & launch on an Android device/emulator once built."
	@echo "            Run 'make build-mobile' for the toolchain preflight + exact steps."
	@echo "            See docs/mobile.md."
	@exit 2

# ----------------------------------------------------------------------------
# Model eval / benchmarks / leakage / gold / sync — later stages
# Placeholders exit non-zero so they are never mistaken for a passing check.
# ----------------------------------------------------------------------------

# AI grader held-out eval + RDKit-only baseline (seeded, re-runnable). Runs via
# the chem-grader venv so the RDKit baseline runs now; the AI grader runs only
# when MECHGRADER_LLM_PROVIDER + a key are set (no AI numbers fabricated
# otherwise). One-time setup: see `make test-grader`. See docs/ai_eval.md.
EVAL_ARGS ?=
.PHONY: eval
eval:
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m mechgrader.eval $(EVAL_ARGS)

# Engine-side dashboard benchmark on a 50k-card collection (p50/p95/worst for the
# Rust topic_mastery query + scoring). Builds & caches the collection under
# out/mechgrader_bench/. GUI-interaction metrics need the app (see docs/results.md).
BENCH_ARGS ?=
.PHONY: bench
bench:
	$(PY) -m mechgrader.bench $(BENCH_ARGS)

# Near-duplicate / leakage scan (canonical SMILES + InChIKey + Morgan Tanimoto)
# over the gold set: no held-out reaction may appear in training/few-shot/
# calibration inputs. Needs RDKit (chem-grader/.venv; see `make test-grader`).
.PHONY: leakage
leakage:
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m mechgrader.leakage

.PHONY: gold
gold:
	@echo "[MechGrader] 'gold' is scaffolded for Stage 2 (build/refresh data/gold_mechanisms + data/gold_qa)."
	@exit 2

.PHONY: sync-server
sync-server:
	@echo "[MechGrader] 'sync-server' is scaffolded for Stage 2 (self-hosted Anki sync server)."
	@echo "            Will wrap 'just' / anki's built-in syncserver. See docs/sync_conflict_rule.md."
	@exit 2
