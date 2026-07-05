#!/usr/bin/env python3
"""Stage 0 proof: exercise the new Rust ``MechgraderService.MechgraderEngineInfo``
RPC end-to-end from Python, through the exact same ``_rsbridge`` FFI that the
desktop Qt GUI uses to talk to the forked engine.

This is the honest, re-runnable substitute for "watch a log line appear in the
GUI": a headless CI box has no display, but this call travels the identical
Python -> rsbridge -> Rust Backend -> Collection path the GUI would, so a
successful, non-empty response proves the fork's engine change is live.

Run from the repo root:

    PYTHONPATH=out/pylib out/pyenv/bin/python mechgrader/tools/stage0_engine_probe.py
"""

from __future__ import annotations

import os
import tempfile

import anki.collection


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        col = anki.collection.Collection(os.path.join(d, "stage0.anki2"))
        try:
            resp = col._backend.mechgrader_engine_info()
        finally:
            col.close()

    print("info        :", resp.info)
    print("anki_version :", resp.anki_version)
    print("build_hash   :", resp.build_hash)

    assert "MechGrader engine live" in resp.info, "unexpected engine info"
    assert resp.anki_version, "empty anki_version"
    print("\nOK: forked Rust MechgraderService is reachable from Python via rsbridge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
