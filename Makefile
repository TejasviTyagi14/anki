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
PYENV := out/pyenv/bin/python
PY    := PYTHONPATH=out/pylib $(PYENV)

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

.PHONY: test-anki
test-anki:
	just test

# MechGrader engine tests (fast subset that covers the fork's Rust change).
.PHONY: test
test:
	cargo test -p anki --lib mechgrader
	$(PY) mechgrader/tools/stage0_engine_probe.py

# Stage 0 gate proof, runnable on its own.
.PHONY: stage0-proof
stage0-proof:
	cargo test -p anki --lib mechgrader
	$(PY) mechgrader/tools/stage0_engine_probe.py

# ----------------------------------------------------------------------------
# Mobile (AnkiDroid fork on the shared engine) — see docs/mobile.md
# ----------------------------------------------------------------------------

.PHONY: build-mobile
build-mobile:
	@echo "[MechGrader] AnkiDroid build is not wired in this environment."
	@echo "            No Android SDK/NDK/JDK is installed here (see 'make help')."
	@echo "            docs/mobile.md documents the exact procedure to rebuild"
	@echo "            rsdroid against this fork's rslib so the Rust change ships to Android."
	@exit 2

.PHONY: run-mobile
run-mobile:
	@echo "[MechGrader] Requires an Android device/emulator + SDK. See docs/mobile.md."
	@exit 2

# ----------------------------------------------------------------------------
# Model eval / benchmarks / leakage / gold / sync — later stages
# Placeholders exit non-zero so they are never mistaken for a passing check.
# ----------------------------------------------------------------------------

.PHONY: eval
eval:
	@echo "[MechGrader] 'eval' is scaffolded for Stage 2 (AI grader held-out eval + RDKit-only baseline)."
	@echo "            Will live in mechgrader/eval/. See docs/ai_eval.md."
	@exit 2

.PHONY: bench
bench:
	@echo "[MechGrader] 'bench' is scaffolded for Stage 3 (50k-card p50/p95/worst-case)."
	@echo "            See docs/results.md (Section 10 targets)."
	@exit 2

.PHONY: leakage
leakage:
	@echo "[MechGrader] 'leakage' is scaffolded for Stage 3 (canonical SMILES + InChIKey + Morgan near-dup scan)."
	@echo "            See docs/results.md and Stage 3 §10.2."
	@exit 2

.PHONY: gold
gold:
	@echo "[MechGrader] 'gold' is scaffolded for Stage 2 (build/refresh data/gold_mechanisms + data/gold_qa)."
	@exit 2

.PHONY: sync-server
sync-server:
	@echo "[MechGrader] 'sync-server' is scaffolded for Stage 2 (self-hosted Anki sync server)."
	@echo "            Will wrap 'just' / anki's built-in syncserver. See docs/sync_conflict_rule.md."
	@exit 2
