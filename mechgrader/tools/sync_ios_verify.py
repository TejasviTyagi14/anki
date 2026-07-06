"""Automated proof of the iOS "Sync card to desktop" path: native phone code
pushes a card to a self-hosted Anki sync server, and a separate desktop
collection then syncs it down.

- The "phone" push runs the SAME `mechgrader_ffi::sync_push` the iOS Swift button
  calls (built natively for the host via `cargo run --example sync_push_demo`).
- The "desktop" side is a plain `anki.collection.Collection` syncing down.

Run:  make sync-ios-verify
Honest scope: both sides run on this machine against a localhost sync server;
it verifies the native sync_push code path end to end (the iOS button calls the
identical function). No network beyond localhost.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD_FRONT = "SN2 mechanism — pushed FROM the phone"
CARD_BACK = "hydroxide + bromomethane (backside attack)"


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


def main() -> int:
    host, port = "127.0.0.1", _free_port()
    endpoint = f"http://{host}:{port}/"
    user, pw = "tester", "pw-abc-12345"
    base = Path(tempfile.mkdtemp(prefix="mg_ios_sync_"))
    phone_dir = base / "phone"
    phone_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("iOS sync verify — native phone push -> self-hosted server -> desktop")
    print(f"server: {endpoint}")
    print("=" * 72)

    env = dict(os.environ)
    env.update(
        SYNC_HOST=host,
        SYNC_PORT=str(port),
        SYNC_BASE=str(base / "server"),
        SYNC_USER1=f"{user}:{pw}",
        MAX_SYNC_PAYLOAD_MEGS="100",
        RUST_LOG="error",
    )

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

        # --- PHONE: run the native FFI sync_push (the iOS button's code) ------
        print("[phone] running native mechgrader_ffi::sync_push ...")
        run = subprocess.run(
            [
                "cargo", "run", "-q", "-p", "mechgrader_ffi",
                "--example", "sync_push_demo", "--",
                str(phone_dir), endpoint, user, pw, CARD_FRONT, CARD_BACK,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        print("[phone] " + (run.stdout or run.stderr).strip())
        if run.returncode != 0:
            print("RESULT: FAIL — native push failed")
            return 1

        # --- DESKTOP: a separate collection syncs down and looks for the card -
        from anki.collection import Collection

        col = Collection(str(base / "desktop.anki2"))
        auth = col.sync_login(user, pw, endpoint)
        out = col.sync_collection(auth, False)
        if out.required in (out.FULL_DOWNLOAD, out.FULL_SYNC):
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
            col.reopen(after_full_sync=True)
        found = len(col.find_notes("phone")) > 0
        n = col.note_count()
        col.close()

        print(f"[desktop] synced down: note_count={n}, phone_card_found={found}")
        print("-" * 72)
        ok = found and n >= 1
        print(
            "RESULT: PASS — a card created on the phone synced to the desktop"
            if ok
            else "RESULT: FAIL — phone card did not reach the desktop"
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
