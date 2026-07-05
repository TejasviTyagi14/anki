#!/usr/bin/env python3
"""Stage-2 (logic) proof for the mechanism-attempt sync + conflict rule.

Implements the gate in ``docs/sync_conflict_rule.md`` deterministically, with no
network and no real device: pure stdlib, so desktop and mobile would run the
identical merge. Runs two ways (either is fine):

    python3 mechgrader/tests/test_sync_conflict.py
    python3 -m pytest mechgrader/tests/test_sync_conflict.py -q

The guarantees under test (the honesty contract — no lost or double-counted
reviews; deterministic, correct winner):

* Two devices, same card, DIFFERENT attempts offline -> after merge BOTH are
  present and the per-card count is exactly right (no loss, no double count).
* The SAME attempt updated on both devices -> the higher LOGICAL timestamp wins
  and the overridden write is recorded in the conflict log (never dropped).
* A device with a WRONG wall clock but a LOWER logical timestamp LOSES — the
  logical stamp decides, not the device clock (a naive wall-clock rule would
  have picked the wrong winner; we assert that too).
* Merge is idempotent and order-independent (and associative): replaying or
  reordering ops always converges to the same winning set + conflict log.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mechgrader.sync.attempts import (  # noqa: E402
    Attempt,
    AttemptStore,
    ConflictEntry,
    merge,
)
from mechgrader.sync.clock import LogicalClock, restamp, stamp_attempt  # noqa: E402

# Wall-clock readings (epoch seconds). CORRECT is ~2026-07-05; WRONG_FUTURE is a
# badly-skewed phone clock ~2100. WRONG_FUTURE > CORRECT on purpose, so a naive
# wall-clock last-write-wins would (incorrectly) let the skewed phone win.
CORRECT_WALL = 1_751_731_920
WRONG_FUTURE_WALL = 4_102_444_800


# --- helpers ---------------------------------------------------------------
def _uuid() -> str:
    return str(uuid.uuid4())


def _attempt(
    attempt_id: str,
    card_id,
    device_id: str,
    logical_ts: int,
    grade: str,
    *,
    wall=None,
    mechanism=None,
) -> Attempt:
    """A minimal Attempt whose payload carries a mechanism + a grade."""
    return Attempt(
        attempt_id=attempt_id,
        card_id=card_id,
        device_id=device_id,
        logical_ts=logical_ts,
        payload={"mechanism": mechanism or {"steps": [grade]}, "grade": grade},
        device_wall_clock=wall,
    )


def _grade_of(attempt: Attempt) -> str:
    return attempt.payload["grade"]


def _wall_clock_winner(a: Attempt, b: Attempt) -> Attempt:
    """What a NAIVE (wrong) rule would pick: the larger device wall clock.

    Used only to demonstrate that our logical-ts rule diverges from — and is
    safer than — trusting the device clock. Never used in production merges.
    """
    return a if (a.device_wall_clock or 0) >= (b.device_wall_clock or 0) else b


def _rich_stores():
    """Two stores exercising every case: distinct attempts, updated-on-both,
    and an identical attempt present on both sides.

        card 'A': a1 (only local), a2 (only remote), a3 (updated on both)
        card 'B': b1 (updated on both), b2 (identical on both)
    """
    a1 = _attempt("a1", "A", "desktop", 3, "correct")
    a2 = _attempt("a2", "A", "phone", 4, "partial")
    a3_local = _attempt("a3", "A", "desktop", 5, "partial")
    a3_remote = _attempt("a3", "A", "phone", 8, "correct")
    b1_local = _attempt("b1", "B", "desktop", 10, "correct")
    b1_remote = _attempt("b1", "B", "phone", 3, "wrong")
    b2 = _attempt("b2", "B", "desktop", 2, "correct")

    local = AttemptStore([a1, a3_local, b1_local, b2])
    remote = AttemptStore([a2, a3_remote, b1_remote, b2])
    return local, remote


# --- 1. distinct attempts on the same card are BOTH retained ----------------
def test_distinct_attempts_same_card_both_retained():
    card = "card-1"
    server = LogicalClock()
    # Two devices, offline, each make a DIFFERENT attempt (different UUIDs) on
    # the same card; the server stamps them as they arrive.
    desktop_attempt = stamp_attempt(
        server, attempt_id=_uuid(), card_id=card, device_id="desktop",
        payload={"mechanism": {"steps": ["SN2"]}, "grade": "correct"},
        device_wall_clock=CORRECT_WALL,
    )
    phone_attempt = stamp_attempt(
        server, attempt_id=_uuid(), card_id=card, device_id="phone",
        payload={"mechanism": {"steps": ["SN2-alt"]}, "grade": "partial"},
        device_wall_clock=CORRECT_WALL,
    )
    assert desktop_attempt.attempt_id != phone_attempt.attempt_id

    local = AttemptStore([desktop_attempt])
    remote = AttemptStore([phone_attempt])
    merged, conflicts = merge(local, remote)

    # BOTH attempts survive; the count is exactly 2 (no loss, no double count).
    assert merged.count_for_card(card) == 2, merged.attempts_for_card(card)
    assert len(merged) == 2
    assert merged.version_count == 2  # nothing duplicated
    ids = {a.attempt_id for a in merged.attempts_for_card(card)}
    assert ids == {desktop_attempt.attempt_id, phone_attempt.attempt_id}
    # Different attempts are NOT a conflict.
    assert conflicts == []
    print(
        f"  [1] two offline attempts on {card!r} both retained: "
        f"count={merged.count_for_card(card)} conflicts={len(conflicts)}"
    )


# --- 2. same attempt updated on both -> higher logical ts wins + logged ------
def test_same_attempt_update_higher_logical_ts_wins_and_is_logged():
    card = "card-1"
    attempt_id = _uuid()
    # Same attempt (same UUID) edited on both devices while offline; the server
    # stamps the two updates as they arrive (desktop first -> lower stamp).
    server = LogicalClock()
    desktop_v = stamp_attempt(
        server, attempt_id=attempt_id, card_id=card, device_id="desktop",
        payload={"mechanism": {"steps": ["v-desktop"]}, "grade": "partial"},
        device_wall_clock=CORRECT_WALL,
    )
    phone_v = stamp_attempt(
        server, attempt_id=attempt_id, card_id=card, device_id="phone",
        payload={"mechanism": {"steps": ["v-phone"]}, "grade": "correct"},
        device_wall_clock=CORRECT_WALL,
    )
    assert phone_v.logical_ts > desktop_v.logical_ts

    merged, conflicts = merge(AttemptStore([desktop_v]), AttemptStore([phone_v]))

    # Exactly one record for the attempt (updates are NOT double-counted).
    assert merged.count_for_card(card) == 1
    winner = merged.winners()[attempt_id]
    assert winner.logical_ts == phone_v.logical_ts
    assert _grade_of(winner) == "correct"  # the higher-stamp write

    # The overridden write is preserved in full in the conflict log.
    assert len(conflicts) == 1
    entry = conflicts[0]
    assert isinstance(entry, ConflictEntry)
    assert entry.attempt_id == attempt_id
    assert entry.overridden.logical_ts == desktop_v.logical_ts
    assert _grade_of(entry.overridden) == "partial"
    assert entry.winner.logical_ts == phone_v.logical_ts
    assert "logical" in entry.reason.lower()
    print(
        f"  [2] same attempt updated on both -> winner logical_ts="
        f"{winner.logical_ts} grade={_grade_of(winner)!r}; overridden "
        f"logical_ts={entry.overridden.logical_ts} logged (not dropped)"
    )


# --- 3. wrong wall clock but lower logical ts -> LOSES -----------------------
def test_wrong_wall_clock_loses_to_higher_logical_ts():
    card = "card-2"
    attempt_id = _uuid()
    server = LogicalClock()
    # The PHONE reaches the server first (lower logical stamp) but its clock is
    # badly wrong (set to ~2100). The desktop update arrives later (higher
    # stamp) with a correct clock.
    phone_v = stamp_attempt(
        server, attempt_id=attempt_id, card_id=card, device_id="phone",
        payload={"mechanism": {"steps": ["phone-wrong-clock"]}, "grade": "wrong"},
        device_wall_clock=WRONG_FUTURE_WALL,
    )
    desktop_v = stamp_attempt(
        server, attempt_id=attempt_id, card_id=card, device_id="desktop",
        payload={"mechanism": {"steps": ["desktop-correct"]}, "grade": "correct"},
        device_wall_clock=CORRECT_WALL,
    )
    assert phone_v.logical_ts < desktop_v.logical_ts
    # A naive wall-clock rule WOULD pick the phone (its clock is in the future).
    assert _wall_clock_winner(phone_v, desktop_v) is phone_v

    merged, conflicts = merge(AttemptStore([phone_v]), AttemptStore([desktop_v]))

    # ...but the logical timestamp decides, so the desktop (higher stamp) wins.
    winner = merged.winners()[attempt_id]
    assert winner.device_id == "desktop"
    assert _grade_of(winner) == "correct"
    assert merged.count_for_card(card) == 1
    # The skewed phone write lost and is recorded, not silently discarded.
    assert len(conflicts) == 1
    assert conflicts[0].overridden.device_id == "phone"
    assert conflicts[0].overridden.device_wall_clock == WRONG_FUTURE_WALL
    print(
        f"  [3] wrong-clock phone (wall={WRONG_FUTURE_WALL}, logical_ts="
        f"{phone_v.logical_ts}) LOSES to desktop (logical_ts={desktop_v.logical_ts}); "
        f"logical ts decides, not wall clock"
    )


# --- 4. merge is idempotent -------------------------------------------------
def test_merge_is_idempotent():
    local, remote = _rich_stores()
    first = merge(local, remote)
    # Replaying `remote` (or `local`) again changes nothing.
    replay_remote = merge(first.merged, remote)
    replay_local = merge(first.merged, local)

    assert replay_remote.merged == first.merged  # merge(merge(a,b), b) == merge(a,b)
    assert replay_local.merged == first.merged
    assert replay_remote.merged.winners() == first.merged.winners()
    assert replay_remote.conflict_log == first.conflict_log
    # Merging the converged store with itself is also a no-op.
    assert merge(first.merged, first.merged).merged == first.merged
    print(
        f"  [4] idempotent: merge(merge(a,b),b) == merge(a,b) "
        f"(attempts={len(first.merged)}, conflicts={len(first.conflict_log)})"
    )


# --- 5. merge is order-independent ------------------------------------------
def test_merge_is_order_independent():
    local, remote = _rich_stores()
    ab = merge(local, remote)
    ba = merge(remote, local)

    # Full converged state matches...
    assert ab.merged == ba.merged
    # ...and so does the winning set explicitly (the property the spec names)...
    assert ab.merged.winners() == ba.merged.winners()
    # ...and the conflict log (deterministically ordered).
    assert ab.conflict_log == ba.conflict_log
    # Spot-check the winners are the higher-stamp writes regardless of side.
    assert ab.merged.winners()["a3"].logical_ts == 8
    assert ab.merged.winners()["b1"].logical_ts == 10
    print(
        f"  [5] order-independent: merge(a,b) == merge(b,a); "
        f"winners a3@{ab.merged.winners()['a3'].logical_ts}, "
        f"b1@{ab.merged.winners()['b1'].logical_ts}"
    )


# --- 6. merge is associative (strengthens the CRDT claim) -------------------
def test_merge_is_associative():
    a, b = _rich_stores()
    # A third store: a further update to a3 and a brand-new attempt.
    c = AttemptStore(
        [
            _attempt("a3", "A", "tablet", 12, "correct"),  # newest update to a3
            _attempt("c1", "A", "tablet", 6, "partial"),   # a distinct attempt
        ]
    )
    left = merge(merge(a, b).merged, c)
    right = merge(a, merge(b, c).merged)

    assert left.merged == right.merged
    assert left.merged.winners() == right.merged.winners()
    assert left.conflict_log == right.conflict_log
    # a3 now resolves to the highest stamp across all three stores.
    assert left.merged.winners()["a3"].logical_ts == 12
    assert left.merged.count_for_card("A") == 4  # a1, a2, a3, c1
    print(
        f"  [6] associative: (a·b)·c == a·(b·c); a3 winner logical_ts="
        f"{left.merged.winners()['a3'].logical_ts}, card A count="
        f"{left.merged.count_for_card('A')}"
    )


# --- 7. replaying merges never inflates the per-card count -------------------
def test_no_double_count_across_replays():
    local, remote = _rich_stores()
    merged = merge(local, remote).merged
    base_a = merged.count_for_card("A")
    base_b = merged.count_for_card("B")
    # Re-merge many times, in both orders; counts must not drift.
    for _ in range(5):
        merged = merge(merged, remote).merged
        merged = merge(local, merged).merged
    assert merged.count_for_card("A") == base_a == 3
    assert merged.count_for_card("B") == base_b == 2
    print(
        f"  [7] no double-count across replays: card A stays {base_a}, "
        f"card B stays {base_b}"
    )


# --- 8. the device wall clock never affects the merge -----------------------
def test_wall_clock_is_ignored_in_identity_and_merge():
    # Two records identical except for their (irrelevant) device wall clock.
    base = _attempt("same", "A", "desktop", 5, "correct", wall=CORRECT_WALL)
    skewed = replace(base, device_wall_clock=WRONG_FUTURE_WALL)
    assert base == skewed  # wall clock excluded from equality
    assert base.identity() == skewed.identity()

    merged, conflicts = merge(AttemptStore([base]), AttemptStore([skewed]))
    # They collapse to a single version — not treated as two writes/conflict.
    assert merged.version_count == 1
    assert merged.count_for_card("A") == 1
    assert conflicts == []
    print("  [8] identical writes differing only by wall clock collapse to one")


# --- 9. LogicalClock is monotonic; observe never goes backward ---------------
def test_logical_clock_monotonic_and_observe():
    clock = LogicalClock()
    stamps = [clock.tick() for _ in range(4)]
    assert stamps == [1, 2, 3, 4]
    assert clock.value == 4
    # observe() jumps ahead of a higher seen stamp...
    assert clock.observe(10) == 10
    assert clock.tick() == 11
    # ...but never rewinds for a lower one.
    assert clock.observe(3) == 11
    assert clock.tick() == 12
    print("  [9] logical clock strictly increases; observe() never rewinds")


# --- 10. stamp_attempt uses the logical clock, not the wall clock ------------
def test_stamp_attempt_uses_logical_not_wall_clock():
    server = LogicalClock()
    first = stamp_attempt(
        server, attempt_id=_uuid(), card_id="A", device_id="phone",
        payload={"mechanism": {}, "grade": "correct"},
        device_wall_clock=WRONG_FUTURE_WALL,  # huge, but must not matter
    )
    second = stamp_attempt(
        server, attempt_id=_uuid(), card_id="A", device_id="desktop",
        payload={"mechanism": {}, "grade": "correct"},
        device_wall_clock=CORRECT_WALL,  # smaller wall clock
    )
    # Ordering follows the logical clock (1, 2), independent of wall clocks.
    assert (first.logical_ts, second.logical_ts) == (1, 2)
    assert second.order_key > first.order_key
    # restamp advances the logical stamp but keeps the attempt identity.
    updated = restamp(server, first)
    assert updated.attempt_id == first.attempt_id
    assert updated.logical_ts == 3 > first.logical_ts
    print("  [10] stamp_attempt/restamp order by logical clock, not wall clock")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\nOK: {len(tests)} sync-conflict tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
