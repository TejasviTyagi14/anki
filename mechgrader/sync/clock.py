"""The logical clock that stamps attempts — never the device wall clock.

``docs/sync_conflict_rule.md`` fixes the conflict rule: last-write-wins ordered
by a **logical / server-assigned timestamp**, so "a phone with a wrong clock
cannot win incorrectly." This module provides that timestamp source and the
helper that applies it.

* :class:`LogicalClock` is a monotonic counter. In production it lives on the
  Anki sync server (or the companion attempt-sync service) and stamps each
  attempt as it is received *at sync time*. It only ever moves forward, and
  :meth:`LogicalClock.observe` lets a node advance past any stamp it has already
  seen (Lamport-style) so the order stays consistent across devices.
* :func:`stamp_attempt` and :func:`restamp` produce/refresh an
  :class:`~mechgrader.sync.attempts.Attempt` using that logical stamp. The
  device wall clock, if supplied, is stored as *metadata only* and is provably
  ignored by the merge (it is excluded from attempt equality and ordering).

Honesty note: this file is the single place a timestamp used for ordering is
minted. It deliberately offers no path to derive that ordering stamp from a
device clock, so a skewed/wrong client clock cannot change who wins.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional, Union

from .attempts import Attempt, AttemptId, CardId

__all__ = ["LogicalClock", "stamp_attempt", "restamp"]


class LogicalClock:
    """A monotonic counter that assigns logical/server timestamps.

    Not thread-safe by design (kept minimal and deterministic); wrap externally
    if shared. Starts at ``start`` and yields ``start + 1`` on the first tick.
    """

    __slots__ = ("_value",)

    def __init__(self, start: int = 0) -> None:
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError(f"LogicalClock start must be an int, got {start!r}")
        self._value = start

    @property
    def value(self) -> int:
        """The most recently issued stamp (0 / ``start`` before the first tick)."""
        return self._value

    def tick(self) -> int:
        """Advance and return the next logical timestamp (strictly increasing)."""
        self._value += 1
        return self._value

    def observe(self, seen_ts: int) -> int:
        """Advance so the next :meth:`tick` exceeds a stamp already seen.

        Lamport merge rule: after observing a remote stamp, this clock never
        issues a value ``<=`` it, keeping the global order monotonic even when
        stamps arrive out of band. Returns the (possibly unchanged) current
        value; it never moves the clock backward.
        """
        if isinstance(seen_ts, bool) or not isinstance(seen_ts, int):
            raise TypeError(f"observe() expects an int stamp, got {seen_ts!r}")
        if seen_ts > self._value:
            self._value = seen_ts
        return self._value


def stamp_attempt(
    clock: LogicalClock,
    *,
    attempt_id: AttemptId,
    card_id: CardId,
    device_id: str,
    payload: Mapping[str, Any],
    device_wall_clock: Optional[Union[float, int]] = None,
) -> Attempt:
    """Create an :class:`Attempt` stamped with a fresh logical timestamp.

    The stamp comes from ``clock`` (the server/logical counter), NOT from
    ``device_wall_clock``. The wall clock, if given, is attached only as
    metadata for display and is excluded from every merge decision.
    """
    if not isinstance(clock, LogicalClock):
        raise TypeError("stamp_attempt() requires a LogicalClock")
    return Attempt(
        attempt_id=attempt_id,
        card_id=card_id,
        device_id=device_id,
        logical_ts=clock.tick(),
        payload=payload,
        device_wall_clock=device_wall_clock,
    )


def restamp(clock: LogicalClock, attempt: Attempt) -> Attempt:
    """Return a copy of ``attempt`` with a new (higher) logical timestamp.

    Models the server re-stamping an *update to the same attempt* at sync time:
    the ``attempt_id`` is preserved (so it reconciles against the original), only
    the logical stamp advances. The device wall clock is left untouched and,
    again, is never used for ordering.
    """
    if not isinstance(clock, LogicalClock):
        raise TypeError("restamp() requires a LogicalClock")
    if not isinstance(attempt, Attempt):
        raise TypeError("restamp() requires an Attempt")
    return replace(attempt, logical_ts=clock.tick())
