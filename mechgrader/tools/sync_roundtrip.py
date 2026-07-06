"""Real two-collection sync round-trip through Anki's OWN self-hosted sync server.

This proves the shared engine's sync actually works end to end (not just the
conflict-merge logic in ``mechgrader/sync/``): a note created on collection **A**
is uploaded to a local ``RustBackend.syncserver`` and then appears on a separate
collection **B** after B syncs down. Both the server and both clients are the
SAME forked Rust engine (via the ``anki`` Python bindings), so this is the
desktop analogue of a desktop<->phone sync against a self-hosted server.

Run:  make sync-roundtrip
Honest scope: this is a real client<->server<->client round-trip on one machine
(two separate collection files + the real Anki sync protocol). It is NOT a
two-physical-device test; the phone client wiring is tracked separately
(docs/mobile.md). No network beyond localhost.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(host: str, port: int, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), 0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _full_sync(col, auth, out, *, upload: bool) -> None:
    """Perform the full up/down transfer the way the desktop (aqt) does."""
    if upload:
        col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
    else:
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        col.reopen(after_full_sync=True)


def _sync(col, auth, *, prefer_upload: bool) -> str:
    """One sync; if the server asks for a full sync, do it in the given direction."""
    out = col.sync_collection(auth, False)  # sync_media=False
    req = out.required
    full = {out.FULL_SYNC, out.FULL_UPLOAD, out.FULL_DOWNLOAD}
    if req in full:
        _full_sync(col, auth, out, upload=prefer_upload)
        return "full-upload" if prefer_upload else "full-download"
    if req == out.NO_CHANGES:
        return "no-changes"
    return "normal-sync"


def main() -> int:
    from anki.collection import Collection

    host, port = "127.0.0.1", _free_port()
    endpoint = f"http://{host}:{port}/"
    user, pw = "tester", "pw-abc-12345"
    base = Path(tempfile.mkdtemp(prefix="mg_sync_"))

    env = dict(os.environ)
    env.update(
        SYNC_HOST=host,
        SYNC_PORT=str(port),
        SYNC_BASE=str(base / "server"),
        SYNC_USER1=f"{user}:{pw}",
        MAX_SYNC_PAYLOAD_MEGS="100",
        RUST_LOG="error",
    )

    print("=" * 70)
    print("MechGrader sync round-trip — collection A -> self-hosted server -> B")
    print(f"server: {endpoint}   base: {base}")
    print("=" * 70)

    server = subprocess.Popen(
        [sys.executable, "-m", "anki.syncserver"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        if not _wait_port(host, port):
            log = server.stdout.read().decode() if server.stdout else ""
            print("sync server did not start:\n" + log)
            return 1
        print(f"[server] listening on {host}:{port}")

        # --- Collection A: add a MechGrader card, sync UP ------------------
        col_a = Collection(str(base / "a.anki2"))
        nt = col_a.models.by_name("Basic") or col_a.models.all()[0]
        note = col_a.new_note(nt)
        note.fields[0] = "MechGrader SN2 sync-probe"
        if len(note.fields) > 1:
            note.fields[1] = "hydroxide + bromomethane"
        col_a.add_note(note, col_a.decks.id("MechGrader"))
        a_notes = col_a.note_count()
        auth_a = col_a.sync_login(user, pw, endpoint)
        action_a = _sync(col_a, auth_a, prefer_upload=True)
        print(f"[A] notes={a_notes}; first sync -> {action_a}")
        col_a.close()

        # --- Collection B: fresh, sync DOWN, verify the card arrived ------
        col_b = Collection(str(base / "b.anki2"))
        b_before = col_b.note_count()
        auth_b = col_b.sync_login(user, pw, endpoint)
        action_b = _sync(col_b, auth_b, prefer_upload=False)
        b_after = col_b.note_count()
        found = len(col_b.find_notes("SN2 sync-probe")) > 0
        print(f"[B] notes before={b_before}; sync -> {action_b}; after={b_after}; card_found={found}")
        col_b.close()

        ok = action_a == "full-upload" and b_after >= a_notes and found
        print("-" * 70)
        print(
            "RESULT: PASS — note created on A synced through the server to B"
            if ok
            else "RESULT: FAIL — note did not round-trip"
        )
        return 0 if ok else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
