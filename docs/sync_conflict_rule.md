# Sync & conflict rule

Covers standard Anki collection sync plus MechGrader's new data (mechanism
drawings + grades). Implemented in Stage 2; the rule is fixed here now.

## Transport
- **Collection/scheduling data:** ride Anki's native sync via a self-hosted Anki
  sync server (`make sync-server`), shared by desktop and the AnkiDroid fork.
- **Mechanism attempts (new data):** prefer riding Anki's native sync by storing
  each attempt in a synced structure **keyed by `card_id` + a per-attempt UUID**
  (so attempts merge as a set, not a scalar). If that proves impractical, a small
  companion attempt-sync service with the same auth is the documented fallback.
  Either way: **no lost or double-counted reviews.**

## Offline
- Review + draw + store attempts fully offline. Offline grading uses the
  deterministic **RDKit-JS** path. The full AI rubric grade is queued and applied
  when back online. Sync resumes when the connection returns.

## Conflict rule (same card reviewed on two devices offline)
**Last-write-wins by a logical/server-assigned timestamp — never the raw device
clock.** Concretely:
- Each attempt/review carries a **monotonic logical counter** and is stamped by
  the **server clock** at sync time; ordering uses these, so a phone with a wrong
  clock cannot win incorrectly.
- The write with the higher logical stamp wins; the loser is **not discarded
  silently** — it is recorded in a **conflict log** the app can display
  ("sync-conflict-resolved" notice).
- Because mechanism attempts are keyed by `card_id + UUID`, two offline attempts
  on the same card on two devices are **both retained** (they are different
  attempts); "last-write-wins" applies only to genuine updates of the *same*
  attempt/record, and to scalar per-card state that Anki already reconciles.

## What we must prove (Stage 2 gate)
- A card reviewed on the phone appears on desktop after sync, and vice versa.
- The conflict scenario picks a clear, correct winner and logs the override.
- A phone offline mid-sync, or with a wrong clock, still converges correctly
  (logical timestamps).

## Status
Documented. Implementation + proof in Stage 2.
