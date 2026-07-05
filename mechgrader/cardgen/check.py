"""Deterministic quality check for AI-generated MechCards (rubric item 7f).

The contract is honesty-first: a *wrong* card is worse than no card, so this
checker never guesses in a card's favour. It compares a generated card's answer
against a gold Q&A set (known-correct answers plus ``acceptable_variants``) and
sorts every card into exactly three buckets:

* ``correct_useful`` — the answer matches a known-correct answer AND the card
  teaches something (question is specific, not a duplicate, not trivial).
* ``wrong`` — a factual contradiction (e.g. Markovnikov vs anti-Markovnikov) OR
  an answer that cannot be verified against the gold answer or any acceptable
  variant. Both are treated as wrong on purpose (see "conservatism" below).
* ``bad_teaching`` — correct-but-vague/trivial/duplicate (or unverifiable for a
  lack of a matching gold item).

:func:`run_cardgen_check` returns the three counts, the pass/fail decision
against a **pre-registered** cutoff (see ``PREREGISTERED.md`` /
:data:`DEFAULT_PASS_CUTOFF`), and the list of cards to block
(:func:`blocked_cards`).

Conservatism (why this is honest): matching is deterministic and one-directional.
If ``acceptable_variants`` is incomplete, a genuinely-correct card can be marked
``wrong`` (lost recall) — but a wrong fact can never be marked correct. Failing
safe is the point.

Pure stdlib, deterministic, offline. No model is in this loop.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "PassCutoff",
    "DEFAULT_PASS_CUTOFF",
    "VERDICTS",
    "normalize",
    "answer_matches",
    "contradicts",
    "triviality_reasons",
    "is_trivial",
    "question_similarity",
    "near_duplicate_pairs",
    "duplicate_indices",
    "classify_card",
    "run_cardgen_check",
    "blocked_cards",
    "load_gold_items",
]

VERDICTS = ("correct_useful", "wrong", "bad_teaching")


# --------------------------------------------------------------------------- #
# Pre-registered cutoff (mirrors PREREGISTERED.md; drift between the two is a bug)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PassCutoff:
    """The pre-registered passing bar. A batch passes only if ALL hold:

    * ``correct_useful`` fraction ``>= min_correct_useful_frac``
    * ``wrong`` count ``<= max_wrong``  (0 = a single wrong card fails the batch)
    * ``bad_teaching`` fraction ``<= max_bad_teaching_frac``
    """

    min_correct_useful_frac: float = 0.90
    max_wrong: int = 0
    max_bad_teaching_frac: float = 0.10
    preregistered_ref: str = "mechgrader/cardgen/PREREGISTERED.md"

    def as_dict(self) -> dict:
        return {
            "min_correct_useful_frac": self.min_correct_useful_frac,
            "max_wrong": self.max_wrong,
            "max_bad_teaching_frac": self.max_bad_teaching_frac,
            "preregistered_ref": self.preregistered_ref,
        }


DEFAULT_PASS_CUTOFF = PassCutoff()


def _coerce_cutoff(pass_cutoff: Any) -> dict:
    if pass_cutoff is None:
        return DEFAULT_PASS_CUTOFF.as_dict()
    if isinstance(pass_cutoff, PassCutoff):
        return pass_cutoff.as_dict()
    if isinstance(pass_cutoff, dict):
        d = DEFAULT_PASS_CUTOFF.as_dict()
        return {
            "min_correct_useful_frac": float(
                pass_cutoff.get("min_correct_useful_frac", d["min_correct_useful_frac"])
            ),
            "max_wrong": int(pass_cutoff.get("max_wrong", d["max_wrong"])),
            "max_bad_teaching_frac": float(
                pass_cutoff.get("max_bad_teaching_frac", d["max_bad_teaching_frac"])
            ),
            "preregistered_ref": pass_cutoff.get("preregistered_ref", d["preregistered_ref"]),
        }
    raise TypeError("pass_cutoff must be None, a PassCutoff, or a dict")


# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Grammatical stop-words only (never domain terms), so removing them cannot
# change the chemistry a phrase asserts.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "to", "in", "is", "are", "was", "were", "be",
        "and", "or", "that", "this", "it", "its", "as", "by", "with", "for",
        "on", "at", "into", "from", "which", "will", "does", "do", "when",
    }
)


def normalize(text: Any) -> str:
    """Lower-case, strip accents/punctuation, and collapse whitespace.

    Hyphens/underscores/slashes become spaces so ``anti-Markovnikov`` tokenises
    as ``anti markovnikov``. Combining marks are dropped (``Bürgi`` -> ``burgi``)
    and stray symbols (``°``, ``~``) are removed.
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'")
    s = s.lower()
    s = re.sub(r"[-_/]", " ", s)
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _content_tokens(text: Any) -> list:
    return [t for t in normalize(text).split() if t not in _STOPWORDS]


# --------------------------------------------------------------------------- #
# Factual comparison: match vs contradiction
# --------------------------------------------------------------------------- #
def _accepted_norms(gold_item: dict) -> list:
    """Normalised gold answer + acceptable variants (non-empty)."""
    values = [gold_item.get("answer", "")]
    values += list(gold_item.get("acceptable_variants") or [])
    out = []
    for value in values:
        norm = normalize(value)
        if norm:
            out.append(norm)
    return out


def answer_matches(generated_answer: Any, gold_item: dict, *, overlap: float = 0.8) -> bool:
    """True if ``generated_answer`` matches the gold answer or a variant.

    Deterministic, order-independent match: exact normalised equality, an
    accepted multi-word phrase appearing inside the answer, all of an accepted
    phrase's content tokens being present, or >= ``overlap`` token coverage of an
    accepted phrase. This is intentionally *not* fuzzy on meaning — semantic
    opposites are caught by :func:`contradicts`, which callers run first.
    """
    gen_norm = normalize(generated_answer)
    if not gen_norm:
        return False
    gen_tokens = set(_content_tokens(generated_answer))
    for accepted in _accepted_norms(gold_item):
        if accepted == gen_norm:
            return True
        accepted_tokens = [t for t in accepted.split() if t not in _STOPWORDS]
        token_set = set(accepted_tokens)
        if len(accepted_tokens) >= 2 and accepted in gen_norm:
            return True
        if token_set and token_set <= gen_tokens:
            return True
        if token_set and len(token_set & gen_tokens) / len(token_set) >= overlap:
            return True
    return False


# Semantic opposites in orgo mechanisms. If the gold answer sits on exactly one
# side and the card asserts the other, that is a wrong fact even if most words
# match. Keep pairs unambiguous (no accidental substring overlap).
_ANTONYM_GROUPS = (
    frozenset({"inversion", "retention"}),
    frozenset({"inverted", "retained"}),
    frozenset({"increase", "decrease"}),
    frozenset({"increases", "decreases"}),
    frozenset({"faster", "slower"}),
    frozenset({"stronger", "weaker"}),
    frozenset({"primary", "tertiary"}),
    frozenset({"exothermic", "endothermic"}),
    frozenset({"exergonic", "endergonic"}),
    frozenset({"oxidation", "reduction"}),
    frozenset({"oxidized", "reduced"}),
    frozenset({"oxidised", "reduced"}),
    frozenset({"protonation", "deprotonation"}),
    frozenset({"protonated", "deprotonated"}),
    frozenset({"nucleophile", "electrophile"}),
    frozenset({"nucleophilic", "electrophilic"}),
    frozenset({"cis", "trans"}),
    frozenset({"syn", "anti"}),
    frozenset({"concerted", "stepwise"}),
    frozenset({"keto", "enol"}),
)

_NEGATIONS = frozenset(
    {"not", "no", "never", "cannot", "cant", "without", "neither", "nor", "none", "isnt", "doesnt", "dont"}
)


def _markovnikov_side(norm_text: str) -> Optional[str]:
    """'anti' if the text says anti-Markovnikov, 'plain' if Markovnikov, else None."""
    if "anti markovnikov" in norm_text:
        return "anti"
    if "markovnikov" in norm_text:
        return "plain"
    return None


def contradicts(gold_answer: Any, generated_answer: Any) -> list:
    """Return human-readable reasons the card *contradicts* the gold answer.

    Anchored on the canonical gold ``answer`` (not the variants). Empty list
    means "no contradiction detected" (which is NOT the same as "matches").
    """
    gold = normalize(gold_answer)
    gen = normalize(generated_answer)
    gold_tokens = set(gold.split())
    gen_tokens = set(gen.split())
    reasons: list = []

    gold_mark, gen_mark = _markovnikov_side(gold), _markovnikov_side(gen)
    if gold_mark and gen_mark and gold_mark != gen_mark:
        label = {"anti": "anti-Markovnikov", "plain": "Markovnikov"}
        reasons.append(f"gold is {label[gold_mark]} but card says {label[gen_mark]}")

    # EAS directors: meta vs ortho/para.
    gold_meta, gold_op = "meta" in gold_tokens, bool({"ortho", "para"} & gold_tokens)
    gen_meta, gen_op = "meta" in gen_tokens, bool({"ortho", "para"} & gen_tokens)
    if gold_meta and not gold_op and gen_op and not gen_meta:
        reasons.append("gold says meta-directing but card says ortho/para")
    if gold_op and not gold_meta and gen_meta and not gen_op:
        reasons.append("gold says ortho/para-directing but card says meta")

    for group in _ANTONYM_GROUPS:
        gold_side = [w for w in group if w in gold_tokens]
        if len(gold_side) != 1:
            continue
        opposite = (group - {gold_side[0]}) & gen_tokens
        if opposite:
            reasons.append(f"gold says '{gold_side[0]}' but card says '{sorted(opposite)[0]}'")

    # Negation flip on otherwise-similar answers ("inverts" vs "does not invert").
    if bool(gold_tokens & _NEGATIONS) != bool(gen_tokens & _NEGATIONS):
        gold_content = {w for w in gold_tokens if w not in _NEGATIONS and w not in _STOPWORDS}
        gen_content = {w for w in gen_tokens if w not in _NEGATIONS and w not in _STOPWORDS}
        if gold_content and gen_content:
            jaccard = len(gold_content & gen_content) / len(gold_content | gen_content)
            if jaccard >= 0.6:
                reasons.append("card negates the gold fact")

    return reasons


# --------------------------------------------------------------------------- #
# Teaching-quality heuristics
# --------------------------------------------------------------------------- #
_VAGUE_ANSWERS = frozenset(
    {
        "it depends", "depends", "varies", "various", "many factors",
        "several factors", "stuff", "things", "idk", "maybe", "sometimes", "n a",
    }
)
_GENERIC_QUESTIONS = frozenset(
    {"explain", "describe", "discuss", "why", "how", "what", "what is it", "what is this"}
)


def triviality_reasons(question: Any, answer: Any) -> list:
    """Why a (factually-correct) card teaches poorly; empty means it is fine.

    Flags vague/too-short/generic questions, questions that give the answer away
    (all answer content tokens already appear in the question), and vague filler
    answers. Duplicate detection is separate (a set-level property).
    """
    q_norm = normalize(question)
    a_norm = normalize(answer)
    q_tokens = q_norm.split()
    reasons: list = []

    if not q_norm:
        return ["question is empty"]
    if len(q_tokens) < 3:
        reasons.append("question is too short to test understanding")
    if q_norm in _GENERIC_QUESTIONS or q_norm.startswith("what about"):
        reasons.append("question is vague/generic")

    answer_content = [t for t in a_norm.split() if t not in _STOPWORDS]
    question_content = {t for t in q_tokens if t not in _STOPWORDS}
    if answer_content and set(answer_content) <= question_content:
        reasons.append("question already contains the answer (gives it away)")

    if a_norm in _VAGUE_ANSWERS:
        reasons.append("answer is vague filler")
    if answer_content and answer_content[0] in {"yes", "no", "true", "false"} and len(answer_content) == 1:
        reasons.append("answer is a bare yes/no")

    return reasons


def is_trivial(question: Any, answer: Any) -> bool:
    """Convenience boolean over :func:`triviality_reasons`."""
    return bool(triviality_reasons(question, answer))


# --------------------------------------------------------------------------- #
# Near-duplicate detection over a set of cards
# --------------------------------------------------------------------------- #
def question_similarity(question_a: Any, question_b: Any) -> float:
    """Jaccard token similarity of two questions in ``[0, 1]`` (1.0 if identical)."""
    if normalize(question_a) == normalize(question_b) and normalize(question_a):
        return 1.0
    set_a = set(_content_tokens(question_a))
    set_b = set(_content_tokens(question_b))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _question_of(card: Any) -> str:
    return (card or {}).get("question", "") if isinstance(card, dict) else ""


def near_duplicate_pairs(cards: list, *, threshold: float = 0.85) -> list:
    """All ``(i, j, similarity)`` pairs whose questions are near-duplicates."""
    pairs = []
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            similarity = question_similarity(_question_of(cards[i]), _question_of(cards[j]))
            if similarity >= threshold:
                pairs.append((i, j, similarity))
    return pairs


def duplicate_indices(cards: list, *, threshold: float = 0.85) -> dict:
    """Map each duplicate card's index to the earliest index it duplicates.

    The first occurrence of a question is kept; later near-duplicates are the
    ones flagged (``{later_index: earliest_index}``).
    """
    duplicates: dict = {}
    for j in range(len(cards)):
        for i in range(j):
            if question_similarity(_question_of(cards[i]), _question_of(cards[j])) >= threshold:
                duplicates[j] = i
                break
    return duplicates


# --------------------------------------------------------------------------- #
# Per-card classification
# --------------------------------------------------------------------------- #
def classify_card(generated_card: dict, gold_item: dict) -> dict:
    """Classify one generated card against its matched gold item.

    Returns ``{"verdict": <one of VERDICTS>, "reasons": [str, ...]}``. Order of
    checks encodes the honesty policy: a contradiction or an unverifiable answer
    is ``wrong`` *before* teaching quality is ever considered.
    """
    card = generated_card or {}
    gen_question = card.get("question", "")
    gen_answer = card.get("answer", "")
    gold_answer = (gold_item or {}).get("answer", "")

    if not str(gen_answer).strip():
        return {"verdict": "wrong", "reasons": ["generated card has no answer to verify"]}

    contradiction = contradicts(gold_answer, gen_answer)
    if contradiction:
        return {"verdict": "wrong", "reasons": ["factual contradiction: " + "; ".join(contradiction)]}

    if not answer_matches(gen_answer, gold_item):
        return {
            "verdict": "wrong",
            "reasons": [
                "answer cannot be verified against the gold answer or any "
                f"acceptable variant (gold answer: {gold_answer!r})"
            ],
        }

    teaching = triviality_reasons(gen_question, gen_answer)
    if teaching:
        return {"verdict": "bad_teaching", "reasons": teaching}

    return {"verdict": "correct_useful", "reasons": ["answer matches a known-correct answer"]}


# --------------------------------------------------------------------------- #
# Pairing generated cards to gold items
# --------------------------------------------------------------------------- #
def _pair_gold(card: dict, gold_items: list, gold_by_id: dict, *, threshold: float = 0.6):
    """Find the gold item a card should be checked against, or ``None``.

    Prefers an explicit ``gold_id`` on the card, then an exact normalised
    question match, then the most similar question above ``threshold``.
    """
    card = card or {}
    gold_id = card.get("gold_id")
    if gold_id is not None and str(gold_id) in gold_by_id:
        return gold_by_id[str(gold_id)]

    q_norm = normalize(card.get("question", ""))
    if q_norm:
        for gold in gold_items:
            if normalize((gold or {}).get("question", "")) == q_norm:
                return gold

    best, best_similarity = None, 0.0
    for gold in gold_items:
        similarity = question_similarity(card.get("question", ""), (gold or {}).get("question", ""))
        if similarity > best_similarity:
            best, best_similarity = gold, similarity
    return best if best is not None and best_similarity >= threshold else None


# --------------------------------------------------------------------------- #
# Batch check + report
# --------------------------------------------------------------------------- #
def run_cardgen_check(
    generated_cards: list,
    gold_items: list,
    *,
    pass_cutoff: Any = None,
    dup_threshold: float = 0.85,
) -> dict:
    """Check a batch of generated cards against the gold set.

    Returns a report with the THREE COUNTS, the pass/fail decision against
    ``pass_cutoff`` (defaults to the pre-registered :data:`DEFAULT_PASS_CUTOFF`),
    per-card results, and the list of blocked cards. A card that duplicates an
    earlier one is downgraded to ``bad_teaching`` (unless it is already
    ``wrong`` — a wrong fact dominates a duplicate).
    """
    cutoff = _coerce_cutoff(pass_cutoff)
    gold_by_id = {
        str(g["id"]): g for g in gold_items if isinstance(g, dict) and g.get("id") is not None
    }

    results: list = []
    for index, card in enumerate(generated_cards):
        card = card or {}
        gold = _pair_gold(card, gold_items, gold_by_id)
        if gold is None:
            results.append(
                {
                    "index": index,
                    "card_id": card.get("id"),
                    "gold_id": None,
                    "question": card.get("question", ""),
                    "answer": card.get("answer", ""),
                    "verdict": "bad_teaching",
                    "reasons": ["no matching gold Q&A item to verify this card against"],
                }
            )
            continue
        verdict = classify_card(card, gold)
        results.append(
            {
                "index": index,
                "card_id": card.get("id"),
                "gold_id": gold.get("id"),
                "question": card.get("question", ""),
                "answer": card.get("answer", ""),
                "verdict": verdict["verdict"],
                "reasons": list(verdict["reasons"]),
            }
        )

    for later, earliest in duplicate_indices(generated_cards, threshold=dup_threshold).items():
        result = results[later]
        if result["verdict"] == "wrong":
            continue
        origin = results[earliest].get("card_id")
        origin_label = origin if origin is not None else f"index {earliest}"
        result["verdict"] = "bad_teaching"
        # Drop the now-irrelevant "correct" note so the blocked reason is clear.
        result["reasons"] = [r for r in result["reasons"] if "matches a known-correct" not in r]
        if not any("duplicate" in reason for reason in result["reasons"]):
            result["reasons"].append(f"near-duplicate of card {origin_label}")

    counts = {"correct_useful": 0, "wrong": 0, "bad_teaching": 0}
    for result in results:
        counts[result["verdict"]] += 1

    total = len(results)
    cu_frac = counts["correct_useful"] / total if total else 0.0
    wrong_frac = counts["wrong"] / total if total else 0.0
    bad_frac = counts["bad_teaching"] / total if total else 0.0

    cutoff_checks = {
        "correct_useful_frac_ok": cu_frac >= cutoff["min_correct_useful_frac"],
        "wrong_ok": counts["wrong"] <= cutoff["max_wrong"],
        "bad_teaching_frac_ok": bad_frac <= cutoff["max_bad_teaching_frac"],
    }
    passed = total > 0 and all(cutoff_checks.values())

    reasons: list = []
    if total == 0:
        reasons.append("no cards to check")
    if not cutoff_checks["wrong_ok"]:
        reasons.append(
            f"{counts['wrong']} wrong card(s) present; cutoff tolerates {cutoff['max_wrong']} "
            "(a wrong fact is worse than no card)"
        )
    if not cutoff_checks["correct_useful_frac_ok"]:
        reasons.append(
            f"only {cu_frac:.0%} correct-useful; need >= {cutoff['min_correct_useful_frac']:.0%}"
        )
    if not cutoff_checks["bad_teaching_frac_ok"]:
        reasons.append(
            f"{bad_frac:.0%} bad-teaching; cutoff allows <= {cutoff['max_bad_teaching_frac']:.0%}"
        )
    if passed:
        reasons.append("meets the pre-registered cutoff")

    blocked = [result for result in results if result["verdict"] != "correct_useful"]

    return {
        "total": total,
        "counts": counts,
        "fractions": {
            "correct_useful": cu_frac,
            "wrong": wrong_frac,
            "bad_teaching": bad_frac,
        },
        "passed": passed,
        "pass_cutoff": cutoff,
        "cutoff_checks": cutoff_checks,
        "results": results,
        "blocked": blocked,
        "reasons": reasons,
    }


def blocked_cards(report: dict) -> list:
    """The cards a batch must block (every ``wrong`` and ``bad_teaching`` card)."""
    return list((report or {}).get("blocked", []))


# --------------------------------------------------------------------------- #
# Gold-set loader
# --------------------------------------------------------------------------- #
_DEFAULT_GOLD_PATH = Path(__file__).resolve().parents[2] / "data" / "gold_qa" / "gold_qa.json"


def load_gold_items(path: Any = None) -> list:
    """Load the gold Q&A items from ``data/gold_qa/gold_qa.json`` (or ``path``).

    Accepts either a bare JSON list or an object with an ``items`` list.
    """
    gold_path = Path(path) if path is not None else _DEFAULT_GOLD_PATH
    with open(gold_path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return list(data.get("items", []))
    return list(data)
