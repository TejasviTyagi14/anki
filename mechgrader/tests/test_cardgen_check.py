#!/usr/bin/env python3
"""Tests for the card-generation quality check (rubric item 7f).

Pure stdlib, deterministic, offline. **No API key, no network.** Runs two ways:

    python3 mechgrader/tests/test_cardgen_check.py
    python3 -m pytest mechgrader/tests/test_cardgen_check.py -q

What is proven here (the honesty contract):

* A card with a WRONG fact is classified ``wrong`` and BLOCKED.
* A correct-but-vague card and a duplicate card are ``bad_teaching`` and blocked.
* The three counts (correct_useful / wrong / bad_teaching) are exactly right.
* ``run_cardgen_check`` FAILS the pre-registered cutoff when any wrong card is
  present (even at 90% correct), and PASSES an all-good batch.
* The LLM generation seam is key-gated and injectable: it raises without a key
  and never touches the network in tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mechgrader.cardgen import generate  # noqa: E402
from mechgrader.cardgen.check import (  # noqa: E402
    DEFAULT_PASS_CUTOFF,
    VERDICTS,
    blocked_cards,
    classify_card,
    duplicate_indices,
    is_trivial,
    load_gold_items,
    near_duplicate_pairs,
    run_cardgen_check,
    triviality_reasons,
)

REQUIRED_GOLD_KEYS = {"id", "source_ref", "question", "answer", "acceptable_variants", "notes"}


# --------------------------------------------------------------------------- #
# Synthetic fixtures: a mixed batch with hand-known verdicts.
# --------------------------------------------------------------------------- #
def _inline_gold() -> list:
    return [
        {
            "id": "g-sn2-inv",
            "source_ref": "clayden-2ed#ch15.2",
            "question": "In an SN2 reaction, what is the stereochemical outcome at the reacting carbon?",
            "answer": "inversion of configuration",
            "acceptable_variants": ["inversion", "Walden inversion", "the configuration is inverted"],
            "notes": "tie to backside attack",
        },
        {
            "id": "g-sn1-rds",
            "source_ref": "clayden-2ed#ch15.3",
            "question": "Which single step controls the overall rate of an SN1 reaction?",
            "answer": "formation of the carbocation",
            "acceptable_variants": ["carbocation formation", "ionization", "loss of the leaving group to form a carbocation"],
            "notes": "the slow ionization step",
        },
        {
            "id": "g-mark",
            "source_ref": "wade-9ed#ch8.3",
            "question": "What regiochemistry does HBr addition to an alkene follow without peroxides?",
            "answer": "Markovnikov",
            "acceptable_variants": ["Markovnikov addition", "H adds to the carbon with more hydrogens"],
            "notes": "more stable carbocation",
        },
        {
            "id": "g-eas-dir",
            "source_ref": "carey-11ed#ch12.11",
            "question": "Are alkyl groups ortho/para or meta directors in electrophilic aromatic substitution?",
            "answer": "ortho/para directors",
            "acceptable_variants": ["ortho and para directors", "o/p directors"],
            "notes": "activators are o/p directing",
        },
        {
            "id": "g-hydride",
            "source_ref": "wade-9ed#ch18.9",
            "question": "What product forms when a ketone is reduced by NaBH4?",
            "answer": "a secondary alcohol",
            "acceptable_variants": ["secondary alcohol", "2 degree alcohol"],
            "notes": "hydride adds to the carbonyl carbon",
        },
    ]


def _mixed_cards() -> list:
    """Order matters: the duplicate is placed AFTER the card it duplicates."""
    return [
        # C1 — correct + useful
        {
            "id": "c1",
            "gold_id": "g-sn2-inv",
            "question": "When a nucleophile performs an SN2 substitution, how does the configuration at the reacting carbon change?",
            "answer": "The configuration is inverted (Walden inversion).",
        },
        # C2 — correct + useful
        {
            "id": "c2",
            "gold_id": "g-sn1-rds",
            "question": "Which single step controls the overall rate of an SN1 reaction?",
            "answer": "The rate-determining step is formation of the carbocation (ionization).",
        },
        # C3 — WRONG fact (should be Markovnikov)
        {
            "id": "c3",
            "gold_id": "g-mark",
            "question": "Predict the regiochemistry when HBr adds to propene with no peroxides present.",
            "answer": "Anti-Markovnikov addition.",
        },
        # C4 — WRONG fact (alkyl groups are o/p directors, not meta)
        {
            "id": "c4",
            "gold_id": "g-eas-dir",
            "question": "Do alkyl substituents direct an incoming electrophile to the meta position?",
            "answer": "Yes, alkyl groups are meta directors.",
        },
        # C5 — correct answer but VAGUE question -> bad_teaching
        {
            "id": "c5",
            "gold_id": "g-hydride",
            "question": "SN1?",
            "answer": "a secondary alcohol",
        },
        # C6 — correct + useful
        {
            "id": "c6",
            "gold_id": "g-hydride",
            "question": "What is the product of reducing a ketone with sodium borohydride (NaBH4)?",
            "answer": "A secondary alcohol.",
        },
        # C7 — DUPLICATE of C2's question -> bad_teaching
        {
            "id": "c7",
            "gold_id": "g-sn1-rds",
            "question": "Which single step controls the overall rate of an SN1 reaction?",
            "answer": "Carbocation formation.",
        },
    ]


def _correct_card_from(gold: dict, *, card_id: str) -> dict:
    """A card that echoes a gold item -> guaranteed correct + useful."""
    return {
        "id": card_id,
        "gold_id": gold["id"],
        "question": gold["question"],
        "answer": gold["answer"],
    }


# --------------------------------------------------------------------------- #
# 1. The gold deliverable itself.
# --------------------------------------------------------------------------- #
def test_gold_set_has_at_least_50_valid_items():
    items = load_gold_items()
    assert len(items) >= 50, f"gold set must have >= 50 items, has {len(items)}"

    ids = [it["id"] for it in items]
    assert len(set(ids)) == len(ids), "gold ids must be unique"

    for it in items:
        assert REQUIRED_GOLD_KEYS <= set(it), f"{it.get('id')!r} missing keys"
        assert str(it["question"]).strip(), f"{it['id']} has empty question"
        assert str(it["answer"]).strip(), f"{it['id']} has empty answer"
        assert str(it["source_ref"]).strip() and "#" in it["source_ref"], (
            f"{it['id']} needs a '<source_id>#<locator>' source_ref"
        )
        assert isinstance(it["acceptable_variants"], list)


def test_checker_runs_against_real_gold_items():
    gold = load_gold_items()
    by_id = {it["id"]: it for it in gold}

    # A correct echo of a real gold item is correct_useful...
    sn2 = by_id["qa-0001"]
    good = classify_card(
        {"gold_id": sn2["id"], "question": sn2["question"], "answer": sn2["answer"]}, sn2
    )
    assert good["verdict"] == "correct_useful"

    # ...and a deliberately contradictory answer against the same item is wrong.
    bad = classify_card(
        {"gold_id": sn2["id"], "question": sn2["question"], "answer": "retention of configuration"},
        sn2,
    )
    assert bad["verdict"] == "wrong"


# --------------------------------------------------------------------------- #
# 2. Per-card classification.
# --------------------------------------------------------------------------- #
def test_classify_returns_valid_schema():
    gold = _inline_gold()[0]
    result = classify_card({"question": "q?", "answer": "inversion"}, gold)
    assert set(result) == {"verdict", "reasons"}
    assert result["verdict"] in VERDICTS
    assert isinstance(result["reasons"], list) and result["reasons"]


def test_correct_card_is_correct_useful():
    gold = {g["id"]: g for g in _inline_gold()}
    cards = {c["id"]: c for c in _mixed_cards()}
    assert classify_card(cards["c1"], gold["g-sn2-inv"])["verdict"] == "correct_useful"
    assert classify_card(cards["c2"], gold["g-sn1-rds"])["verdict"] == "correct_useful"
    assert classify_card(cards["c6"], gold["g-hydride"])["verdict"] == "correct_useful"


def test_wrong_fact_card_is_classified_wrong():
    gold = {g["id"]: g for g in _inline_gold()}
    cards = {c["id"]: c for c in _mixed_cards()}
    # anti-Markovnikov vs Markovnikov
    c3 = classify_card(cards["c3"], gold["g-mark"])
    assert c3["verdict"] == "wrong"
    assert "contradiction" in " ".join(c3["reasons"]).lower()
    # meta vs ortho/para
    assert classify_card(cards["c4"], gold["g-eas-dir"])["verdict"] == "wrong"


def test_unverifiable_answer_is_wrong_not_silently_passed():
    gold = _inline_gold()[1]  # SN1 rds
    result = classify_card({"question": "What is the SN1 slow step?", "answer": "the solvent evaporates"}, gold)
    assert result["verdict"] == "wrong"


def test_vague_correct_card_is_bad_teaching():
    gold = {g["id"]: g for g in _inline_gold()}
    cards = {c["id"]: c for c in _mixed_cards()}
    result = classify_card(cards["c5"], gold["g-hydride"])
    assert result["verdict"] == "bad_teaching"


def test_triviality_heuristic():
    # too short / vague / gives-away / bare yes-no
    assert is_trivial("SN1?", "a secondary alcohol")
    assert is_trivial("Explain", "the enolate")
    assert triviality_reasons("Is the enolate the nucleophile, yes or no?", "yes")
    assert triviality_reasons("What is the enolate?", "the enolate")  # answer given away
    # a specific question with a substantive answer is NOT trivial
    assert not is_trivial(
        "What nucleophile adds to the electrophilic carbonyl in an aldol addition?",
        "an enolate",
    )


# --------------------------------------------------------------------------- #
# 3. Duplicate detection over a set.
# --------------------------------------------------------------------------- #
def test_near_duplicate_detection():
    cards = _mixed_cards()
    dups = duplicate_indices(cards)
    # C7 (index 6) duplicates C2 (index 1); nothing else.
    assert dups == {6: 1}
    pairs = near_duplicate_pairs(cards)
    assert any(i == 1 and j == 6 for (i, j, _sim) in pairs)


# --------------------------------------------------------------------------- #
# 4. Batch report: the THREE COUNTS + pass/fail + blocked list.
# --------------------------------------------------------------------------- #
def test_mixed_batch_counts_and_blocks_and_fails():
    report = run_cardgen_check(_mixed_cards(), _inline_gold())

    assert report["total"] == 7
    assert report["counts"] == {"correct_useful": 3, "wrong": 2, "bad_teaching": 2}

    # A wrong card present -> the batch FAILS the pre-registered cutoff.
    assert report["passed"] is False
    assert report["cutoff_checks"]["wrong_ok"] is False

    # Blocked = every wrong + every bad_teaching card (here: c3, c4, c5, c7).
    blocked = blocked_cards(report)
    blocked_ids = {b["card_id"] for b in blocked}
    assert blocked_ids == {"c3", "c4", "c5", "c7"}
    assert all(b["verdict"] in ("wrong", "bad_teaching") for b in blocked)

    # The wrong cards specifically are blocked.
    wrong_ids = {r["card_id"] for r in report["results"] if r["verdict"] == "wrong"}
    assert wrong_ids == {"c3", "c4"}
    assert wrong_ids <= blocked_ids


def test_all_good_batch_passes():
    gold = load_gold_items()
    by_id = {it["id"]: it for it in gold}
    cards = [
        _correct_card_from(by_id[gid], card_id=f"ok{i}")
        for i, gid in enumerate(["qa-0001", "qa-0006", "qa-0019", "qa-0031", "qa-0040"])
    ]
    report = run_cardgen_check(cards, gold)

    assert report["counts"] == {"correct_useful": 5, "wrong": 0, "bad_teaching": 0}
    assert report["passed"] is True
    assert blocked_cards(report) == []


def test_single_wrong_card_fails_even_at_90pct_correct():
    """max_wrong == 0: one wrong fact fails the batch even when 90% are correct."""
    gold = load_gold_items()
    by_id = {it["id"]: it for it in gold}
    correct_ids = ["qa-0001", "qa-0006", "qa-0014", "qa-0019", "qa-0023",
                   "qa-0031", "qa-0036", "qa-0040", "qa-0046"]
    cards = [_correct_card_from(by_id[gid], card_id=f"g{i}") for i, gid in enumerate(correct_ids)]
    # one wrong card: SN1 favours tertiary, not primary
    cards.append({"id": "bad", "gold_id": "qa-0008", "question": by_id["qa-0008"]["question"], "answer": "primary substrates"})

    report = run_cardgen_check(cards, gold)
    assert report["counts"] == {"correct_useful": 9, "wrong": 1, "bad_teaching": 0}
    assert report["fractions"]["correct_useful"] == 0.9
    # 90% correct clears the fraction bar, but the single wrong card still fails it.
    assert report["cutoff_checks"]["correct_useful_frac_ok"] is True
    assert report["cutoff_checks"]["wrong_ok"] is False
    assert report["passed"] is False


def test_pass_cutoff_is_the_preregistered_one():
    assert DEFAULT_PASS_CUTOFF.min_correct_useful_frac == 0.90
    assert DEFAULT_PASS_CUTOFF.max_wrong == 0
    assert DEFAULT_PASS_CUTOFF.max_bad_teaching_frac == 0.10
    report = run_cardgen_check(_mixed_cards(), _inline_gold())
    assert report["pass_cutoff"]["max_wrong"] == 0
    assert report["pass_cutoff"]["min_correct_useful_frac"] == 0.90


def test_unmatched_card_is_blocked_as_bad_teaching():
    gold = _inline_gold()
    report = run_cardgen_check(
        [{"id": "orphan", "question": "What is the boiling point of benzene?", "answer": "80 C"}], gold
    )
    assert report["counts"]["bad_teaching"] == 1
    assert blocked_cards(report)[0]["card_id"] == "orphan"


# --------------------------------------------------------------------------- #
# 5. The LLM generation SEAM is key-gated + injectable (NO network, NO key).
# --------------------------------------------------------------------------- #
def test_generation_prompt_and_parsing_are_offline():
    messages = generate.build_generation_messages("SOURCE TEXT", n=3, source_ref="clayden-2ed#ch1")
    assert len(messages) == 2 and messages[0]["role"] == "system"
    assert "3" in messages[1]["content"] and "SOURCE TEXT" in messages[1]["content"]
    assert "clayden-2ed#ch1" in messages[1]["content"]

    assert len(generate.parse_generated_cards('[{"question":"q","answer":"a"}]')) == 1
    assert len(generate.parse_generated_cards('{"cards":[{"question":"q","answer":"a"}]}')) == 1
    embedded = 'sure!\n```json\n{"cards":[{"question":"q","answer":"a"}]}\n```'
    assert len(generate.parse_generated_cards(embedded)) == 1


def test_generation_uses_injected_client_without_network_or_key():
    calls = {"n": 0}

    def fake_client(messages, config):
        calls["n"] += 1
        return '{"cards":[{"question":"Why does SN2 invert configuration?","answer":"backside attack"}]}'

    cards = generate.generate_cards(
        "some registered source text",
        n=1,
        source_ref="clayden-2ed#ch15.2",
        client=fake_client,
        config=generate.LLMConfig(api_key=""),  # empty key is fine: no real client is used
    )
    assert calls["n"] == 1
    assert len(cards) == 1
    assert cards[0]["source_ref"] == "clayden-2ed#ch15.2"


def test_generation_is_key_gated():
    """With the default (urllib) client and no key, it raises BEFORE any network."""
    raised = False
    try:
        generate.generate_cards("src", n=1, config=generate.LLMConfig(api_key=""))
    except generate.GenerationConfigError:
        raised = True
    assert raised, "generation must refuse to run without an API key"


# --------------------------------------------------------------------------- #
# Runner (also prints a demonstrative report for the pasted output).
# --------------------------------------------------------------------------- #
def _print_report(title: str, report: dict) -> None:
    counts = report["counts"]
    print(f"\n--- {title} ---")
    print(f"  total={report['total']}  counts={counts}  passed={report['passed']}")
    print(
        "  cutoff: >= {:.0%} correct_useful, <= {} wrong, <= {:.0%} bad_teaching".format(
            report["pass_cutoff"]["min_correct_useful_frac"],
            report["pass_cutoff"]["max_wrong"],
            report["pass_cutoff"]["max_bad_teaching_frac"],
        )
    )
    for reason in report["reasons"]:
        print(f"  decision: {reason}")
    for b in blocked_cards(report):
        print(f"  BLOCKED [{b['verdict']}] {b['card_id']}: {b['reasons'][0]}")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\nOK: {len(tests)} cardgen-check tests passed.")

    # Demonstrative reports (real counts from the checker).
    gold = load_gold_items()
    by_id = {it["id"]: it for it in gold}
    _print_report("mixed batch (has wrong + vague + duplicate)", run_cardgen_check(_mixed_cards(), _inline_gold()))
    all_good = [
        _correct_card_from(by_id[gid], card_id=f"ok{i}")
        for i, gid in enumerate(["qa-0001", "qa-0006", "qa-0019", "qa-0031", "qa-0040"])
    ]
    _print_report("all-good batch", run_cardgen_check(all_good, gold))
    print(f"\ngold_qa items available: {len(gold)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
