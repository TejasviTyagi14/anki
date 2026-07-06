"""Curated practice problems for the four substitution/elimination mechanisms.

Each problem gives the student a starting material + reagents/conditions and asks
them to draw the product and choose the mechanism. The *answer* (acceptable
products) lives here on the server and is never sent to the client, so the UI
can't leak it. Grading reuses the full :class:`~chemgrader.grader.Grader`, so the
same layered chemistry checks apply (it's not string matching).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .feedback import GradeResult
from .grader import Grader, GraderConfig
from .models import (
    MoleculeNode,
    ReactionEdge,
    ReactionGraph,
    normalize_mechanism_type,
)


@dataclass
class Problem:
    id: str
    mechanism: str  # intended mechanism (SN1/SN2/E1/E2)
    title: str
    prompt: str
    start_smiles: str
    reagents: list[str]
    conditions: Optional[str]
    products: list[str]  # acceptable products (answer + valid alternatives) -- HIDDEN
    hint: Optional[str] = None

    def public(self) -> dict:
        """The client-safe view (no answer)."""
        return {
            "id": self.id,
            "mechanism": self.mechanism,
            "title": self.title,
            "prompt": self.prompt,
            "start_smiles": self.start_smiles,
            "reagents": self.reagents,
            "conditions": self.conditions,
            "hint": self.hint,
        }


PROBLEMS: list[Problem] = [
    Problem(
        id="sn2-1",
        mechanism="SN2",
        title="Bromoethane + NaOH",
        prompt="Hydroxide attacks a primary carbon. Draw the substitution product.",
        start_smiles="CCBr",
        reagents=["NaOH"],
        conditions="warm, aqueous",
        products=["CCO"],
        hint="Primary substrate + strong nucleophile favors backside attack.",
    ),
    Problem(
        id="sn2-2",
        mechanism="SN2",
        title="1-Bromobutane + NaSH",
        prompt="A strong sulfur nucleophile displaces bromide. Draw the product.",
        start_smiles="CCCCBr",
        reagents=["NaSH"],
        conditions="polar aprotic",
        products=["CCCCS"],
        hint="Thiolate is an excellent nucleophile; the carbon skeleton is unchanged.",
    ),
    Problem(
        id="sn1-1",
        mechanism="SN1",
        title="tert-Butyl bromide + H2O",
        prompt="A tertiary halide ionizes in water. Draw the substitution product.",
        start_smiles="CC(C)(C)Br",
        reagents=["H2O"],
        conditions="room temperature",
        products=["CC(C)(C)O"],
        hint="Tertiary carbocation forms first, then water traps it.",
    ),
    Problem(
        id="sn1-2",
        mechanism="SN1",
        title="tert-Butyl bromide + methanol",
        prompt="Solvolysis in methanol. Draw the ether product.",
        start_smiles="CC(C)(C)Br",
        reagents=["CH3OH"],
        conditions="reflux",
        products=["COC(C)(C)C"],
        hint="Methanol is the nucleophile in this SN1 solvolysis.",
    ),
    Problem(
        id="e1-1",
        mechanism="E1",
        title="tert-Butyl bromide, EtOH / heat",
        prompt="Same tertiary halide, but hot ethanol favors elimination. Draw the alkene.",
        start_smiles="CC(C)(C)Br",
        reagents=["EtOH"],
        conditions="heat",
        products=["CC(C)=C"],
        hint="Loss of H+ and Br- gives one alkene (the substrate is symmetric).",
    ),
    Problem(
        id="e1-2",
        mechanism="E1",
        title="2-Bromo-2-methylbutane, EtOH / heat",
        prompt="Draw the major (Zaitsev) alkene from this E1 elimination.",
        start_smiles="CCC(C)(Br)C",
        reagents=["EtOH"],
        conditions="heat",
        products=["CC=C(C)C", "CCC(=C)C"],  # Zaitsev (major) + Hofmann (accepted)
        hint="The more substituted alkene (Zaitsev) is favored under E1.",
    ),
    Problem(
        id="e2-1",
        mechanism="E2",
        title="2-Bromopropane + NaOEt",
        prompt="A strong base removes a beta-hydrogen. Draw the alkene.",
        start_smiles="CC(C)Br",
        reagents=["NaOEt"],
        conditions="ethanol",
        products=["CC=C"],
        hint="E2 is concerted: anti-periplanar loss of H and the leaving group.",
    ),
    Problem(
        id="e2-2",
        mechanism="E2",
        title="2-Bromobutane + KOtBu (bulky base)",
        prompt="A bulky base favors the less-substituted (Hofmann) alkene. Draw it.",
        start_smiles="CCC(C)Br",
        reagents=["KOtBu"],
        conditions="tert-butanol",
        products=["CCC=C", "CC=CC"],  # Hofmann (favored by bulky base) + Zaitsev (accepted)
        hint="Bulky bases like tert-butoxide favor the terminal (Hofmann) alkene.",
    ),
]

_BY_ID = {p.id: p for p in PROBLEMS}


def get_problem(problem_id: str) -> Optional[Problem]:
    return _BY_ID.get(problem_id)


def grade_problem(
    problem: Problem,
    product_smiles: str,
    mechanism_type: Optional[str],
    grader: Grader,
    config: Optional[GraderConfig] = None,
) -> GradeResult:
    """Grade a student's single-step answer against the (hidden) reference.

    Grades the attempt against each acceptable product and returns the best
    result, then folds in whether the chosen mechanism matches the intended one
    (which is the whole point of an SN1/SN2/E1/E2 drill).
    """
    attempt = ReactionGraph(
        nodes=[
            MoleculeNode(id="s", smiles=problem.start_smiles),
            MoleculeNode(id="p", smiles=product_smiles),
        ],
        edges=[
            ReactionEdge(
                id="e", source="s", target="p",
                reagents=problem.reagents, mechanism_type=mechanism_type,
            )
        ],
    )

    best: Optional[GradeResult] = None
    for answer in problem.products:
        reference = ReactionGraph(
            nodes=[
                MoleculeNode(id="s", smiles=problem.start_smiles),
                MoleculeNode(id="p", smiles=answer),
            ],
            edges=[
                ReactionEdge(
                    id="e", source="s", target="p",
                    reagents=problem.reagents, mechanism_type=problem.mechanism,
                )
            ],
        )
        result = grader.grade(reference, attempt, config)
        if best is None or result.overall_score > best.overall_score:
            best = result

    assert best is not None
    # Practice drills care about picking the right mechanism, not just the product.
    mechanism_correct = normalize_mechanism_type(mechanism_type) == normalize_mechanism_type(
        problem.mechanism
    )
    if not mechanism_correct:
        best.hints.insert(
            0,
            f"Mechanism: you chose {mechanism_type or '(none)'}, but this is an "
            f"{problem.mechanism} reaction.",
        )
        if best.summary.startswith("Correct"):
            best.summary = "Right product, but the wrong mechanism."
        best.passed = False
        best.breakdown.mechanisms = 0.0
        best.overall_score = round(best.overall_score * 0.6, 4)
    return best
