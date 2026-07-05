"""MechGrader sync: honest, conflict-free merge of mechanism attempts.

This package implements the **mechanism-attempt sync model and the
conflict-resolution logic** fixed in ``docs/sync_conflict_rule.md``. It is the
deterministically testable core; the real two-device transport (a self-hosted
Anki sync server plus the AnkiDroid fork) is documented below and wired in
Stage 2 — it is *not* run here.

What lives here
---------------
* :mod:`mechgrader.sync.attempts` — the :class:`~mechgrader.sync.attempts.Attempt`
  record, the :class:`~mechgrader.sync.attempts.AttemptStore` CRDT, and
  :func:`~mechgrader.sync.attempts.merge` returning ``(merged, conflict_log)``.
* :mod:`mechgrader.sync.clock` — the :class:`~mechgrader.sync.clock.LogicalClock`
  and stamping helpers that assign the ordering timestamp (never the device
  wall clock).

How attempts ride sync (per docs/sync_conflict_rule.md)
-------------------------------------------------------
Mechanism attempts are **new data** (a drawn mechanism + its grade), so they are
modelled as a *set*, not a scalar field:

1. **Preferred — ride Anki's native sync.** Each attempt is stored in a synced
   structure **keyed by ``card_id`` + a per-attempt UUID** (see
   :pyattr:`~mechgrader.sync.attempts.Attempt.storage_key`). Because the key
   includes a globally-unique UUID, two offline attempts on the same card from
   two devices land under two different keys and both survive the sync — they
   merge as a set (:func:`~mechgrader.sync.attempts.merge`), never overwriting
   one another. Collection/scheduling data continues to ride Anki's own sync
   unchanged.
2. **Fallback — a companion attempt-sync service.** If embedding attempts in the
   native sync payload proves impractical, a small companion service using the
   **same auth** as the Anki sync server exchanges attempt sets and applies the
   exact same :func:`~mechgrader.sync.attempts.merge`. Either transport uses this
   identical merge logic, so the guarantee holds both ways: **no lost or
   double-counted reviews.**

The conflict rule (enforced in code here)
-----------------------------------------
* Distinct ``attempt_id`` values are **unioned** — different attempts (even on
  the same card) are all retained and counted once each.
* Genuine updates to the **same** ``attempt_id`` are resolved **last-write-wins
  by the logical/server timestamp** (a monotonic counter), **never** the raw
  device clock — so a phone with a wrong clock cannot win. The overridden write
  is recorded in the **conflict log** the app can display, never dropped.
* Offline attempts are queued locally and merged when back online; the merge is
  idempotent and order-independent, so replaying ops always converges.

What remains for real two-device sync (documented, not run here)
----------------------------------------------------------------
* Stand up the self-hosted Anki sync server (``make sync-server``) and point
  desktop + the AnkiDroid fork at it (shared auth).
* Bind :class:`~mechgrader.sync.clock.LogicalClock` to the server so every
  attempt is stamped server-side at sync time; persist the counter.
* Serialise :class:`~mechgrader.sync.attempts.Attempt` sets into the chosen
  transport (native synced structure, else the companion service) and run
  :func:`~mechgrader.sync.attempts.merge` on receipt.
* Surface the conflict log in the UI as the "sync-conflict-resolved" notice.
* Prove the Stage-2 gate on real devices: a card reviewed on the phone appears
  on desktop and vice versa; the wrong-clock case still converges by logical ts.
"""

from __future__ import annotations

from .attempts import (
    Attempt,
    AttemptId,
    AttemptStore,
    CardId,
    ConflictEntry,
    MergeResult,
    merge,
)
from .clock import LogicalClock, restamp, stamp_attempt

__all__ = [
    "Attempt",
    "AttemptId",
    "AttemptStore",
    "CardId",
    "ConflictEntry",
    "MergeResult",
    "merge",
    "LogicalClock",
    "stamp_attempt",
    "restamp",
]
