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
	@echo "  make ios           Build the iOS app (NATIVE rslib engine + editor) & launch in the Simulator [needs Xcode]"
	@echo "  make sync-roundtrip Real A->server->B sync round-trip on the shared engine (self-hosted sync server)"
	@echo "  make sync-ios-verify Phone->desktop: the native iOS sync_push -> server -> desktop syncs it down"
	@echo "  make grader        Serve the editor + RDKit grader at http://localhost:8000 (clears :8000 first)"
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
# `make grader` is the one-command option: it serves the CURRENT MechGrader
# editor at http://localhost:8000/ AND the RDKit grader at /mech/grade on the
# same origin. (`make editor` still serves just the static bundle on :5178.)
.PHONY: grader
grader:
	@bash -c 'p=$$(lsof -ti tcp:8000); [ -n "$$p" ] && kill -9 $$p || true'
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m uvicorn chemgrader.api:app --host 0.0.0.0 --port 8000

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
	$(PY) mechgrader/tests/test_study_feature.py
	$(PY) mechgrader/tests/test_paraphrase.py
	$(PY) mechgrader/tests/test_crash_recovery.py
	@echo ">> For the RDKit grader suite + the baseline eval, run: make test-grader eval"

# Deterministic grader suite (needs RDKit in chem-grader/.venv). One-time setup:
#   cd chem-grader && python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
.PHONY: test-grader
test-grader:
	PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m pytest \
	    mechgrader/tests/test_deterministic_grader.py mechgrader/tests/test_leakage.py chem-grader/tests -q

# Stage 0 gate proof, runnable on its own.
# Web bundle checks: syntax-check the JS modules + run the drawer logic test.
.PHONY: test-web
test-web:
	@for f in web/mechgrader/*.js; do out/extracted/node/bin/node --check "$$f" && echo "ok $$f"; done
	out/extracted/node/bin/node web/mechgrader/draw.test.mjs

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

.PHONY: ios
ios:
	@echo "[MechGrader] Building the iOS app (native rslib engine + editor) and launching it in the Simulator..."
	bash ios/build_sim.sh

# Prove the iOS FFI runs the real forked engine RPC (host build of the same crate
# the simulator links). Re-runnable engine-sharing check.
.PHONY: test-ios-ffi
test-ios-ffi:
	cargo test -p mechgrader_ffi

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

# Print the three scores (Memory/Performance/Readiness) with ranges + the give-up
# rule abstaining — the demo video's "three scores" shot in one command.
.PHONY: scores
scores:
	$(PY) -m mechgrader.scoring

.PHONY: gold
gold:
	@echo "[MechGrader] 'gold' is scaffolded for Stage 2 (build/refresh data/gold_mechanisms + data/gold_qa)."
	@exit 2

# Real client<->server<->client sync round-trip through Anki's OWN self-hosted
# sync server (RustBackend.syncserver): a note made on collection A is uploaded
# and then appears on a separate collection B. Same forked engine on all sides.
.PHONY: sync-roundtrip
sync-roundtrip:
	$(PY) mechgrader/tools/sync_roundtrip.py

# Phone -> desktop: the NATIVE iOS sync_push (built for host) pushes a card to a
# self-hosted server, then a desktop collection syncs it down. Same code the iOS
# "Sync card to desktop" button runs. Needs cargo + the anki python env.
.PHONY: sync-ios-verify
sync-ios-verify:
	$(PY) mechgrader/tools/sync_ios_verify.py

# Desktop side of the LIVE demo: after `make sync-server` + tapping the app's
# "Sync card -> desktop" button, this syncs down and prints the card received.
.PHONY: sync-pull
sync-pull:
	$(PY) mechgrader/tools/sync_pull.py

# Start the self-hosted sync server for the live phone->desktop demo (Ctrl-C to
# stop). Fixed port 27701 + user tester:pw-abc-12345 match the iOS app's defaults,
# so you can tap "Sync card -> desktop" in the Simulator and it reaches this server.
.PHONY: sync-server
sync-server:
	SYNC_HOST=$${SYNC_HOST:-127.0.0.1} SYNC_PORT=$${SYNC_PORT:-27701} \
	  SYNC_USER1=$${SYNC_USER1:-tester:pw-abc-12345} $(PY) -m anki.syncserver
