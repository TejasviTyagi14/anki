"""Grader behaviour, with emphasis on the tricky cases:

* identical attempt                -> full credit
* wrong final product              -> fails, product not reproduced
* valid alternative route          -> passes, extra intermediate = valid_alternative
* wrong mechanism / right product  -> mechanism flagged, product still reproduced
* right product / unbalanced step  -> conservation error surfaced, step implausible
* stereochemistry mismatch         -> fails strictly, passes with ignore_stereo
"""

from chemgrader import (
    ComparisonOptions,
    Grader,
    GraderConfig,
    MoleculeNode,
    ReactionEdge,
    ReactionGraph,
)
from chemgrader.feedback import NodeStatus

grader = Grader()


def graph(nodes, edges):
    return ReactionGraph(
        nodes=[MoleculeNode(id=i, smiles=s) for i, s in nodes],
        edges=[ReactionEdge(**e) for e in edges],
    )


def node_status(result, node_id):
    return next(n.status for n in result.nodes if n.node_id == node_id)


# --- reference syntheses reused below --------------------------------- #

def _sn2_then_oxidation_ref():
    return graph(
        [("a", "CCBr"), ("b", "CCO"), ("d", "CC(=O)O")],
        [
            {"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"},
            {"id": "e2", "source": "b", "target": "d", "reagents": ["KMnO4"], "mechanism_type": "oxidation"},
        ],
    )


def test_identical_attempt_gets_full_credit():
    ref = _sn2_then_oxidation_ref()
    res = grader.grade(ref, ref.model_copy(deep=True))
    assert res.passed
    assert res.overall_score >= 0.95
    assert all(n.status == NodeStatus.CORRECT for n in res.nodes)


def test_wrong_final_product_fails():
    ref = graph(
        [("a", "CCBr"), ("b", "CCO")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}],
    )
    attempt = graph(
        [("a", "CCBr"), ("b", "CCC")],  # propane, not ethanol
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}],
    )
    res = grader.grade(ref, attempt)
    assert not res.passed
    assert res.breakdown.pathway < 1.0


def test_valid_alternative_route_is_accepted():
    # reference: one-step acid-catalysed hydration of propene to isopropanol
    ref = graph(
        [("a", "C=CC"), ("d", "CC(O)C")],
        [{"id": "e1", "source": "a", "target": "d", "reagents": ["H2O", "H2SO4"],
          "mechanism_type": "electrophilic_addition"}],
    )
    # attempt: propene -> 2-bromopropane -> isopropanol (different but valid route)
    attempt = graph(
        [("a", "C=CC"), ("c", "CC(Br)C"), ("d", "CC(O)C")],
        [
            {"id": "e1", "source": "a", "target": "c", "reagents": ["HBr"],
             "mechanism_type": "electrophilic_addition"},
            {"id": "e2", "source": "c", "target": "d", "reagents": ["NaOH"],
             "mechanism_type": "SN2"},
        ],
    )
    res = grader.grade(ref, attempt)
    assert res.passed
    assert node_status(res, "c") == NodeStatus.VALID_ALTERNATIVE
    assert not any(n.status == NodeStatus.MISSING for n in res.nodes)
    assert res.overall_score >= 0.85


def test_wrong_mechanism_right_product():
    # E2 elimination of bromoethane to ethene, but the student labels it SN2
    ref = graph(
        [("a", "CCBr"), ("b", "C=C")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["KOtBu"], "mechanism_type": "E2"}],
    )
    attempt = graph(
        [("a", "CCBr"), ("b", "C=C")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}],
    )
    res = grader.grade(ref, attempt)
    assert res.edges[0].mechanism_consistent is False
    assert res.breakdown.pathway == 1.0  # product still reproduced
    assert res.overall_score < 1.0
    assert any("mechanism" in h.lower() for h in res.hints)


def test_right_product_but_unbalanced_step():
    ref = _sn2_then_oxidation_ref()
    # reaches acetic acid, but via an intermediate that gains a carbon from nowhere
    attempt = graph(
        [("a", "CCBr"), ("m", "CCCO"), ("d", "CC(=O)O")],
        [
            {"id": "e1", "source": "a", "target": "m", "reagents": ["H2O"]},
            {"id": "e2", "source": "m", "target": "d", "reagents": ["KMnO4"]},
        ],
    )
    res = grader.grade(ref, attempt)
    assert any(not e.conservation_ok for e in res.edges)
    assert not res.passed
    assert any("conserve" in h.lower() for h in res.hints)


def test_stereochemistry_mismatch_toggle():
    ref = graph(
        [("a", "CCC(C)=O"), ("b", "CC[C@H](C)O")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaBH4"], "mechanism_type": "reduction"}],
    )
    attempt = graph(
        [("a", "CCC(C)=O"), ("b", "CC[C@@H](C)O")],  # opposite configuration
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaBH4"], "mechanism_type": "reduction"}],
    )
    strict = grader.grade(ref, attempt)
    assert not strict.passed  # enantiomer is a different structure by default

    lenient = grader.grade(
        ref, attempt, GraderConfig(comparison=ComparisonOptions(ignore_stereo=True))
    )
    assert lenient.passed


def test_invalid_smiles_does_not_crash_grader():
    ref = graph(
        [("a", "CCBr"), ("b", "CCO")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}],
    )
    attempt = graph(
        [("a", "CCBr"), ("b", "not-a-molecule")],
        [{"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}],
    )
    res = grader.grade(ref, attempt)
    assert not res.passed
    assert any(n.status == NodeStatus.INVALID for n in res.nodes)
