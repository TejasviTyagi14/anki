"""Desktop side of the LIVE phone->desktop demo: sync down from the running
self-hosted sync server and print the card(s) the phone pushed.

Live flow (for the demo video):
  1) terminal A:  make sync-server          # fixed port 27701 + tester user
  2) iOS Simulator: tap "Sync card -> desktop"
  3) terminal B:  make sync-pull            # shows the card that arrived

Env overrides: SYNC_ENDPOINT, SYNC_USER, SYNC_PW.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> int:
    from anki.collection import Collection

    endpoint = os.environ.get("SYNC_ENDPOINT", "http://127.0.0.1:27701/")
    user = os.environ.get("SYNC_USER", "tester")
    pw = os.environ.get("SYNC_PW", "pw-abc-12345")

    workdir = Path(tempfile.mkdtemp(prefix="mg_desktop_"))
    col = Collection(str(workdir / "desktop.anki2"))
    try:
        auth = col.sync_login(user, pw, endpoint)
        out = col.sync_collection(auth, False)
        if out.required in (out.FULL_DOWNLOAD, out.FULL_SYNC):
            col.close_for_full_sync()
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
            col.reopen(after_full_sync=True)
        nids = col.find_notes("")
        print(f"desktop synced from {endpoint}: {len(nids)} note(s)")
        for nid in nids[:10]:
            fields = [f for f in col.get_note(nid).fields if f]
            print("  - " + (" | ".join(fields))[:90])
        print("PASS — card(s) received" if nids else "no notes (tap the app's sync button first)")
        return 0 if nids else 1
    finally:
        col.close()


if __name__ == "__main__":
    raise SystemExit(main())
