#!/usr/bin/env python3
"""Stage 3 reliability (10.3): engine-level crash recovery.

Simulates the app dying mid-review and proves the collection never corrupts and
committed data survives:
  A) 20x unclean process exit right after a committed write (os._exit, no close);
  B) a hard SIGKILL while the process is in a tight write loop.
After each, reopen and run SQLite `pragma integrity_check` (definitive) +
Anki's fix_integrity.

This is the headless, engine-level analogue of "kill each app mid-review 20 times,
zero corrupted collections" (the GUI kill needs a display; the durability +
no-corruption guarantee is the collection's, and that is what we test here).

Run:  PYTHONPATH=out/pylib:. out/pyenv/bin/python mechgrader/tests/test_crash_recovery.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

import anki.collection


def _add_one(path: str) -> None:
    col = anki.collection.Collection(path)
    nt = col.models.by_name("Basic")
    note = col.new_note(nt)
    note["Front"] = "prompt"
    note["Back"] = "answer"
    col.add_note(note, col.decks.id("Default"))
    os._exit(0)  # simulate a crash: committed write, but NO clean col.close()


def _write_loop(path: str) -> None:
    col = anki.collection.Collection(path)
    nt = col.models.by_name("Basic")
    did = col.decks.id("Default")
    while True:  # keep writing until SIGKILLed mid-operation
        note = col.new_note(nt)
        note["Front"] = "x"
        note["Back"] = "y"
        col.add_note(note, did)


def _integrity_ok(path: str) -> tuple[bool, int]:
    col = anki.collection.Collection(path)
    try:
        pragma = col.db.scalar("pragma integrity_check")
        _report, fixed_ok = col.fix_integrity()
        n = len(col.find_notes(""))
    finally:
        col.close()
    return (pragma == "ok" and bool(fixed_ok)), n


def _run_parent() -> int:
    env = dict(os.environ)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "crash.anki2")
        anki.collection.Collection(path).close()  # create clean

        # A) 20 unclean exits after a committed write
        for i in range(20):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--add-one", path], env=env)
            assert r.returncode == 0, f"child {i} failed"
        ok, n = _integrity_ok(path)
        assert ok, "collection corrupted after 20 unclean exits"
        assert n == 20, f"expected 20 committed notes, got {n}"
        print(f"A) 20 unclean exits -> integrity OK, {n} notes survived")

        # B) hard SIGKILL mid write-loop
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--write-loop", path], env=env)
        time.sleep(0.8)
        p.kill()  # SIGKILL mid-write
        p.wait()
        ok, n2 = _integrity_ok(path)
        assert ok, "collection corrupted after SIGKILL mid-write"
        assert n2 >= 20, f"committed notes should not be lost, got {n2}"
        print(f"B) SIGKILL mid-write  -> integrity OK, {n2} notes (no corruption)")

    print("\nOK: crash recovery — zero corrupted collections, committed data survived.")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--add-one":
        _add_one(sys.argv[2])  # never returns (os._exit)
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == "--write-loop":
        _write_loop(sys.argv[2])  # runs until killed
        return 0
    return _run_parent()


if __name__ == "__main__":
    raise SystemExit(main())
