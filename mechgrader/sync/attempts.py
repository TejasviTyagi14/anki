"""Mechanism-attempt records and their conflict-free merge.

A mechanism attempt (a drawn mechanism + its grade) is **new data** that
MechGrader adds on top of Anki. Unlike a scalar per-card field, two students'
devices can each produce a *different* attempt on the *same* card while offline,
and **both must survive** the sync — they are different reviews, not a conflict.

The model here is a small CRDT (see ``docs/sync_conflict_rule.md``):

* **State** is a grow-only *set of attempt versions*, deduplicated by a canonical
  content key. Merging two stores is a set union, so it is commutative,
  associative and idempotent — replaying the same ops always converges and
  **nothing is ever lost or double-counted**.
* **Identity** of an attempt is its per-attempt ``attempt_id`` (a UUID). Two
  offline attempts on the same card have *different* UUIDs, so the union keeps
  both. "Last-write-wins" therefore only ever applies to genuine *updates of the
  same attempt_id*.
* **The winner view**: for each ``attempt_id`` the version with the highest
  **logical timestamp** (a server-assigned monotonic counter — never the device
  wall clock; see ``clock.py``) is the current record. Every other version for
  that id is *superseded* and surfaced in the **conflict log** so an override is
  visible ("sync-conflict-resolved"), never silently dropped.

Honesty contract (the rules this file must not break):

* **No lost reviews.** Every distinct ``attempt_id`` ever seen is retained.
* **No double-counted reviews.** Per-card counts use *distinct winning
  attempt_ids*; superseded versions live only in the conflict archive.
* **Deterministic, correct winner.** Ordering is by the logical timestamp, with
  a deterministic content tiebreak — *never* the raw device clock, so a phone
  with a wrong clock cannot win incorrectly.

Pure stdlib, deterministic, offline-capable so desktop and mobile agree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Union

__all__ = [
    "CardId",
    "AttemptId",
    "Attempt",
    "ConflictEntry",
    "MergeResult",
    "AttemptStore",
    "merge",
]

# Anki card ids are integers; we also allow strings so callers/tests are free to
# use readable ids. Whatever type is passed is kept verbatim (never coerced).
CardId = Union[int, str]
AttemptId = str


def _canonical_json(obj: Any) -> str:
    """Stable, key-sorted JSON so equal content always yields equal bytes.

    Used as the deduplication identity of an attempt version and as the final
    (collision-free) tiebreak when two versions somehow share a logical stamp.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Attempt:
    """One versioned mechanism attempt.

    Fields
    ------
    attempt_id : a per-attempt UUID. This is the *identity* of the attempt: two
        different attempts (even on the same card) have different UUIDs and are
        both retained; two versions of the *same* attempt share this id and are
        reconciled by ``logical_ts``.
    card_id : the Anki card this attempt belongs to (the grouping key). Attempts
        are stored "keyed by ``card_id`` + UUID" — see :pyattr:`storage_key`.
    device_id : which device produced this version (for the conflict notice).
    logical_ts : the **server-assigned monotonic logical timestamp** used for
        ordering. Higher wins. This is NOT the device wall clock.
    payload : the actual new data — the drawn ``mechanism`` and its ``grade``.
    device_wall_clock : the device's own clock reading (epoch seconds), recorded
        for display/debugging ONLY. It is excluded from equality, from the
        dedup identity, and from conflict ordering — a wrong device clock can
        never change a merge outcome.
    """

    attempt_id: AttemptId
    card_id: CardId
    device_id: str
    logical_ts: int
    payload: Mapping[str, Any]
    # `compare=False`: the wall clock is metadata only. Excluding it from
    # equality guarantees it can never influence merge/conflict resolution.
    device_wall_clock: Union[float, int, None] = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.attempt_id:
            raise ValueError("Attempt.attempt_id (uuid) is required and non-empty")
        # bool is an int subclass; reject it so True/False can't pose as a stamp.
        if isinstance(self.logical_ts, bool) or not isinstance(self.logical_ts, int):
            raise TypeError(
                f"Attempt.logical_ts must be an int (logical/server stamp), "
                f"got {self.logical_ts!r}"
            )
        if not isinstance(self.payload, Mapping):
            raise TypeError("Attempt.payload must be a mapping (mechanism + grade)")

    @property
    def storage_key(self) -> "tuple[CardId, AttemptId]":
        """The synced-structure key: ``(card_id, attempt_id)``.

        Attempts ride Anki's native sync stored under this key so they merge as
        a *set*, not a scalar (``docs/sync_conflict_rule.md``).
        """
        return (self.card_id, self.attempt_id)

    def identity(self) -> str:
        """Canonical content identity used to deduplicate versions.

        Deliberately excludes ``device_wall_clock`` (metadata). Two versions are
        "the same" iff their id, card, device, logical stamp and payload match.
        """
        return _canonical_json(
            {
                "attempt_id": self.attempt_id,
                "card_id": self.card_id,
                "device_id": self.device_id,
                "logical_ts": self.logical_ts,
                "payload": self.payload,
            }
        )

    @property
    def content_digest(self) -> str:
        """Short stable digest of :meth:`identity` for display/debugging."""
        return hashlib.sha256(self.identity().encode("utf-8")).hexdigest()[:16]

    @property
    def order_key(self) -> "tuple[int, str, str]":
        """Total order for last-write-wins.

        Primary key is the logical timestamp (higher wins). Ties — which a single
        server counter never produces, but which are handled defensively — break
        on ``device_id`` then the full canonical identity. The device wall clock
        is intentionally absent.
        """
        return (self.logical_ts, str(self.device_id), self.identity())


class ConflictEntry(NamedTuple):
    """A recorded override: one attempt version that lost to a later write.

    The overridden write is preserved in full so the app can show a
    "sync-conflict-resolved" notice and the loser is never silently discarded.
    ``winner`` is the version that is now the record for this ``attempt_id``.
    """

    attempt_id: AttemptId
    card_id: CardId
    overridden: Attempt
    winner: Attempt
    reason: str


def _conflict_reason(loser: Attempt, winner: Attempt) -> str:
    return (
        f"attempt {loser.attempt_id} on card {winner.card_id}: write from device "
        f"{loser.device_id!r} (logical_ts={loser.logical_ts}) overridden by device "
        f"{winner.device_id!r} (logical_ts={winner.logical_ts}); resolved by logical "
        f"timestamp, NOT device wall clock"
    )


class AttemptStore:
    """A grow-only set of attempt versions with a last-write-wins winner view.

    Construct from any iterable of :class:`Attempt`. Adding the same version
    twice is a no-op (deduplicated by :meth:`Attempt.identity`), which is what
    makes replays idempotent.

    Two stores are equal iff they hold the same set of versions, so
    ``merge(a, b) == merge(b, a)`` and ``merge(merge(a, b), b) == merge(a, b)``
    hold for the whole state (and therefore for the winning set and the derived
    conflict log).
    """

    __slots__ = ("_versions",)

    def __init__(self, attempts: Iterable[Attempt] = ()) -> None:
        # identity -> Attempt. A dict keyed by canonical identity IS the set.
        self._versions: Dict[str, Attempt] = {}
        for attempt in attempts:
            self.add(attempt)

    # --- building -----------------------------------------------------------
    def add(self, attempt: Attempt) -> None:
        """Add one version. Idempotent: an identical version is absorbed."""
        if not isinstance(attempt, Attempt):
            raise TypeError(f"AttemptStore holds Attempt objects, got {attempt!r}")
        self._versions.setdefault(attempt.identity(), attempt)

    # --- raw state ----------------------------------------------------------
    def versions(self) -> List[Attempt]:
        """Every distinct version held (winners + superseded)."""
        return list(self._versions.values())

    @property
    def version_count(self) -> int:
        """Number of distinct versions (for debugging; NOT the review count)."""
        return len(self._versions)

    def _grouped(self) -> Dict[AttemptId, List[Attempt]]:
        groups: Dict[AttemptId, List[Attempt]] = {}
        for attempt in self._versions.values():
            groups.setdefault(attempt.attempt_id, []).append(attempt)
        return groups

    # --- winner view (the honest current state) -----------------------------
    def winners(self) -> Dict[AttemptId, Attempt]:
        """The current record per ``attempt_id`` — the highest logical stamp."""
        return {
            attempt_id: max(versions, key=lambda a: a.order_key)
            for attempt_id, versions in self._grouped().items()
        }

    def attempts_for_card(self, card_id: CardId) -> List[Attempt]:
        """Winning attempts on a card, sorted by logical timestamp."""
        winners = [a for a in self.winners().values() if a.card_id == card_id]
        return sorted(winners, key=lambda a: a.order_key)

    def count_for_card(self, card_id: CardId) -> int:
        """Honest review count for a card: distinct winning attempts (no dups)."""
        return len(self.attempts_for_card(card_id))

    def superseded(self) -> List[Attempt]:
        """Versions that were overridden — the raw losers behind the log."""
        losers: List[Attempt] = []
        for versions in self._grouped().values():
            if len(versions) <= 1:
                continue
            winner_identity = max(versions, key=lambda a: a.order_key).identity()
            losers.extend(v for v in versions if v.identity() != winner_identity)
        return losers

    def conflict_log(self) -> List[ConflictEntry]:
        """Every override, deterministically ordered.

        Derived purely from the version set, so it is independent of merge order
        and stable across replays. Each entry keeps the overridden write in full.
        """
        entries: List[ConflictEntry] = []
        for attempt_id, versions in self._grouped().items():
            if len(versions) <= 1:
                continue
            winner = max(versions, key=lambda a: a.order_key)
            for loser in versions:
                if loser.identity() == winner.identity():
                    continue
                entries.append(
                    ConflictEntry(
                        attempt_id=attempt_id,
                        card_id=winner.card_id,
                        overridden=loser,
                        winner=winner,
                        reason=_conflict_reason(loser, winner),
                    )
                )
        entries.sort(
            key=lambda e: (str(e.attempt_id), e.overridden.order_key)
        )
        return entries

    # --- convenience --------------------------------------------------------
    def merge(self, other: "AttemptStore") -> "MergeResult":
        """Merge ``other`` into a new store (see module-level :func:`merge`)."""
        return merge(self, other)

    def __len__(self) -> int:
        """Number of distinct attempts (winning records) — the review count."""
        return len(self._grouped())

    def __iter__(self) -> Iterator[Attempt]:
        return iter(self.winners().values())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AttemptStore):
            return NotImplemented
        return self._versions == other._versions

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    # Mutable (grow-only) container: intentionally unhashable.
    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return (
            f"AttemptStore(attempts={len(self)}, versions={self.version_count}, "
            f"conflicts={len(self.conflict_log())})"
        )


class MergeResult(NamedTuple):
    """Return type of :func:`merge`: the converged store + this merge's log.

    Unpacks as ``merged, conflict_log = merge(a, b)`` and also exposes
    ``.merged`` / ``.conflict_log`` for clarity.
    """

    merged: AttemptStore
    conflict_log: List[ConflictEntry]


def merge(local: AttemptStore, remote: AttemptStore) -> MergeResult:
    """Merge two attempt stores into a converged store + a conflict log.

    The merge is a set union of versions, so it is:

    * **lossless** — every distinct ``attempt_id`` from either side survives;
    * **dup-free** — identical versions collapse to one (idempotent replay);
    * **commutative & associative** — ``merge(a, b) == merge(b, a)`` and
      ``merge(merge(a, b), b) == merge(a, b)`` as full states.

    For any ``attempt_id`` updated on both sides, the version with the higher
    **logical timestamp** wins and the loser is returned in ``conflict_log``
    (never dropped). Inputs are not mutated.
    """
    if not isinstance(local, AttemptStore) or not isinstance(remote, AttemptStore):
        raise TypeError("merge() operates on two AttemptStore instances")
    merged = AttemptStore()
    for attempt in local.versions():
        merged.add(attempt)
    for attempt in remote.versions():
        merged.add(attempt)
    return MergeResult(merged, merged.conflict_log())
