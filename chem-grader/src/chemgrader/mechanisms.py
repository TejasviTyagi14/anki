"""A library of mechanism templates and matching logic.

Each :class:`MechanismTemplate` encodes what a mechanism *looks like*:

* substructures that must be present in the reactant (and optionally product),
* the expected change *signature* (bonds formed/broken, change in unsaturation),
* soft reagent hints,
* substrate constraints (e.g. SN2 is implausible at a tertiary carbon).

Matching combines a SMARTS substructure test with the observed
:class:`~chemgrader.transformation.TransformationDiff`. This is deliberately
signature-based rather than full reaction-SMARTS enumeration: enumeration is
brittle for bimolecular steps where the nucleophile comes from the reagents, not
from a graph node. The trade-off (a potential false positive when an unrelated
transformation happens to share a signature) is called out in the README.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem

from .models import MechanismType, normalize_mechanism_type
from .transformation import BondChange, TransformationDiff

_HALOGENS = {"F", "Cl", "Br", "I"}

# A "spec" is a pair of tokens; a token is an element symbol, "X" (any halogen)
# or "*" (any element).
Spec = tuple[str, str]


def _tok_match(token: str, element: str) -> bool:
    if token == "*":
        return True
    if token == "X":
        return element in _HALOGENS
    return token == element


def _pair_matches(change: BondChange, spec: Spec) -> bool:
    a, b = change.element_a, change.element_b
    t1, t2 = spec
    return (_tok_match(t1, a) and _tok_match(t2, b)) or (
        _tok_match(t1, b) and _tok_match(t2, a)
    )


def effective_formed(diff: TransformationDiff) -> list[BondChange]:
    """Bonds formed, including bonds whose order increased (pi bond formation)."""
    out = list(diff.bonds_formed)
    for before, after in diff.order_changes:
        if after.order > before.order:
            out.append(after)
    return out


def effective_broken(diff: TransformationDiff) -> list[BondChange]:
    """Bonds broken, including bonds whose order decreased (pi bond breaking)."""
    out = list(diff.bonds_broken)
    for before, after in diff.order_changes:
        if after.order < before.order:
            out.append(before)
    return out


@dataclass
class MechanismTemplate:
    mechanism_type: MechanismType
    description: str
    reactant_smarts: list[str] = field(default_factory=list)
    product_smarts: list[str] = field(default_factory=list)
    formed_any: list[Spec] = field(default_factory=list)
    broken_any: list[Spec] = field(default_factory=list)
    delta_unsaturation: Optional[int] = None
    # If True, the step must leave the heavy-atom skeleton untouched (only H /
    # charge move). Used for acid-base so it doesn't match every zero-unsaturation
    # transformation.
    no_heavy_change: bool = False
    reagent_hints: list[str] = field(default_factory=list)
    # class -> message. If the leaving-group carbon falls in this class, warn.
    disfavored_classes: dict[str, str] = field(default_factory=dict)
    favored_classes: set[str] = field(default_factory=set)

    # compiled SMARTS cache
    _rc: list = field(default_factory=list, repr=False)
    _pc: list = field(default_factory=list, repr=False)

    def _reactant_queries(self):
        if not self._rc:
            self._rc = [q for q in (Chem.MolFromSmarts(s) for s in self.reactant_smarts) if q]
        return self._rc

    def _product_queries(self):
        if not self._pc:
            self._pc = [q for q in (Chem.MolFromSmarts(s) for s in self.product_smarts) if q]
        return self._pc


@dataclass
class MechanismEvaluation:
    """Result of testing one template against one observed transformation."""

    mechanism_type: MechanismType
    reactant_ok: bool
    signature_ok: bool
    reagent_ok: Optional[bool]
    substrate_warnings: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def consistent(self) -> bool:
        """The mechanism can plausibly produce the observed structural change."""
        return self.reactant_ok and self.signature_ok


def leaving_group_carbon_class(mol: Chem.Mol) -> Optional[str]:
    """Classify the carbon bearing a leaving group as methyl/primary/secondary/tertiary.

    Returns the most-substituted such carbon's class, or ``None`` if there's no
    C-LG site. Used for SN1/SN2/E1/E2 steric/carbocation plausibility.
    """
    lg = Chem.MolFromSmarts("[CX4][F,Cl,Br,I,$([OX2]S(=O)(=O))]")
    if lg is None:
        return None
    best: Optional[str] = None
    order = {"methyl": 0, "primary": 1, "secondary": 2, "tertiary": 3}
    for match in mol.GetSubstructMatches(lg):
        carbon = mol.GetAtomWithIdx(match[0])
        carbon_neighbors = sum(
            1 for nb in carbon.GetNeighbors() if nb.GetSymbol() == "C"
        )
        cls = {0: "methyl", 1: "primary", 2: "secondary", 3: "tertiary"}[carbon_neighbors]
        if best is None or order[cls] > order[best]:
            best = cls
    return best


class MechanismRuleLibrary:
    """Holds mechanism templates and evaluates them against transformations."""

    def __init__(self, templates: Optional[list[MechanismTemplate]] = None):
        self._templates = templates if templates is not None else _default_templates()
        self._by_type = {t.mechanism_type: t for t in self._templates}

    def all(self) -> list[MechanismTemplate]:
        return list(self._templates)

    def get(self, mechanism_type) -> Optional[MechanismTemplate]:
        if isinstance(mechanism_type, str):
            mechanism_type = normalize_mechanism_type(mechanism_type)
        return self._by_type.get(mechanism_type)

    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        template: MechanismTemplate,
        diff: TransformationDiff,
        reactant: Chem.Mol,
        product: Chem.Mol,
        reagents: Optional[list[str]] = None,
    ) -> MechanismEvaluation:
        reagents = reagents or []
        reactant_ok = _has_any(reactant, template._reactant_queries())
        product_ok = True
        if template.product_smarts:
            product_ok = _has_any(product, template._product_queries())

        signature_ok = product_ok
        if template.no_heavy_change:
            signature_ok = signature_ok and (
                not diff.bonds_broken
                and not diff.bonds_formed
                and not diff.order_changes
                and not diff.added_atoms
                and not diff.removed_atoms
            )
        if template.delta_unsaturation is not None:
            signature_ok = signature_ok and (
                diff.delta_unsaturation == template.delta_unsaturation
            )
        if template.broken_any:
            signature_ok = signature_ok and any(
                _pair_matches(c, s) for c in effective_broken(diff) for s in template.broken_any
            )
        if template.formed_any:
            signature_ok = signature_ok and any(
                _pair_matches(c, s) for c in effective_formed(diff) for s in template.formed_any
            )

        reagent_ok: Optional[bool] = None
        if template.reagent_hints:
            joined = " ".join(reagents).lower()
            reagent_ok = any(h in joined for h in template.reagent_hints)

        substrate_warnings: list[str] = []
        if template.disfavored_classes:
            cls = leaving_group_carbon_class(reactant)
            if cls in template.disfavored_classes:
                substrate_warnings.append(template.disfavored_classes[cls])

        confidence = 0.0
        if reactant_ok:
            confidence += 0.4
            if signature_ok:
                confidence += 0.4
            if reagent_ok:
                confidence += 0.2
            cls = leaving_group_carbon_class(reactant)
            if template.favored_classes and cls in template.favored_classes:
                confidence += 0.1
            if substrate_warnings:
                confidence -= 0.2
        confidence = max(0.0, min(1.0, confidence))

        return MechanismEvaluation(
            mechanism_type=template.mechanism_type,
            reactant_ok=reactant_ok,
            signature_ok=bool(signature_ok),
            reagent_ok=reagent_ok,
            substrate_warnings=substrate_warnings,
            confidence=confidence,
        )

    def infer(
        self,
        diff: TransformationDiff,
        reactant: Chem.Mol,
        product: Chem.Mol,
        reagents: Optional[list[str]] = None,
    ) -> list[MechanismEvaluation]:
        """Rank all templates by how well they explain the observed change."""
        evals = [
            self.evaluate(t, diff, reactant, product, reagents) for t in self._templates
        ]
        evals = [e for e in evals if e.confidence > 0]
        evals.sort(key=lambda e: e.confidence, reverse=True)
        return evals


def _has_any(mol: Chem.Mol, queries) -> bool:
    return any(mol.HasSubstructMatch(q) for q in queries)


def _default_templates() -> list[MechanismTemplate]:
    """~11 common MCAT-relevant mechanisms."""
    T = MechanismType
    return [
        MechanismTemplate(
            mechanism_type=T.SN2,
            description="Bimolecular nucleophilic substitution; backside attack, inversion.",
            reactant_smarts=["[CX4][F,Cl,Br,I]", "[CX4][OX2]S(=O)(=O)"],
            formed_any=[("C", "O"), ("C", "N"), ("C", "S"), ("C", "C")],
            broken_any=[("C", "X"), ("C", "O")],
            delta_unsaturation=0,
            reagent_hints=[
                "nacn", "cn", "naoh", "oh-", "hydroxide", "naoet", "etona", "alkoxide",
                "nh3", "amine", "sh", "thiolate", "dmso", "dmf", "acetone", "i-", "nai",
            ],
            disfavored_classes={
                "tertiary": "SN2 at a tertiary carbon is sterically implausible "
                "(backside attack is blocked) -- consider SN1/E1.",
            },
            favored_classes={"methyl", "primary"},
        ),
        MechanismTemplate(
            mechanism_type=T.SN1,
            description="Unimolecular nucleophilic substitution via a carbocation.",
            reactant_smarts=["[CX4][F,Cl,Br,I]", "[CX4][OX2]S(=O)(=O)"],
            formed_any=[("C", "O"), ("C", "N"), ("C", "S")],
            broken_any=[("C", "X"), ("C", "O")],
            delta_unsaturation=0,
            reagent_hints=[
                "h2o", "water", "meoh", "etoh", "protic", "agno3", "ag+", "heat",
            ],
            disfavored_classes={
                "methyl": "SN1 on a methyl carbon is implausible (no carbocation forms).",
                "primary": "SN1 on a primary carbon is implausible "
                "(primary carbocations are too unstable) -- consider SN2.",
            },
            favored_classes={"tertiary"},
        ),
        MechanismTemplate(
            mechanism_type=T.E2,
            description="Bimolecular elimination; anti-periplanar loss of H and LG.",
            reactant_smarts=["[F,Cl,Br,I][CX4][CX4;!H0]"],
            product_smarts=["[CX3]=[CX3]"],
            formed_any=[("C", "C")],  # new/upgraded C=C (via order change)
            broken_any=[("C", "X")],
            delta_unsaturation=1,
            reagent_hints=[
                "kotbu", "otbu", "tert-butoxide", "naoet", "koh", "strong base",
                "ldab", "ldca", "dbu", "naoh", "base",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.E1,
            description="Unimolecular elimination via a carbocation; loss of LG then H.",
            reactant_smarts=["[F,Cl,Br,I][CX4][CX4;!H0]", "[OX2H1][CX4][CX4;!H0]"],
            product_smarts=["[CX3]=[CX3]"],
            formed_any=[("C", "C")],
            broken_any=[("C", "X"), ("C", "O")],
            delta_unsaturation=1,
            reagent_hints=["heat", "h2so4", "h3po4", "protic", "weak base", "h2o"],
            disfavored_classes={
                "primary": "E1 on a primary carbon is implausible "
                "(primary carbocations are too unstable) -- consider E2.",
            },
            favored_classes={"tertiary"},
        ),
        MechanismTemplate(
            mechanism_type=T.ELECTROPHILIC_ADDITION,
            description="Electrophilic addition across a C=C (e.g. HX, X2, acid-catalysed water).",
            reactant_smarts=["[CX3]=[CX3]"],
            formed_any=[("C", "X"), ("C", "O"), ("C", "C"), ("C", "H")],
            delta_unsaturation=-1,
            reagent_hints=[
                "hbr", "hcl", "hi", "h2o", "h3o", "h2so4", "br2", "cl2",
                "bh3", "hydration", "x2",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.NUCLEOPHILIC_ADDITION,
            description="Nucleophilic addition to a carbonyl (C=O -> C-O(-)/C-OH).",
            reactant_smarts=["[CX3]=[OX1]"],
            formed_any=[("C", "C"), ("C", "H"), ("C", "N"), ("C", "O")],
            delta_unsaturation=-1,
            reagent_hints=[
                "grignard", "mgbr", "rli", "nabh4", "lialh4", "hydride",
                "hcn", "cn", "amine", "alcohol",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.NUCLEOPHILIC_ACYL_SUBSTITUTION,
            description="Addition-elimination at a carbonyl bearing a leaving group.",
            reactant_smarts=["[CX3](=[OX1])[Cl,Br,F,OX2,NX3]"],
            product_smarts=["[CX3]=[OX1]"],
            formed_any=[("C", "O"), ("C", "N")],
            broken_any=[("C", "X"), ("C", "O"), ("C", "N")],
            delta_unsaturation=0,
            reagent_hints=[
                "amine", "nh3", "alcohol", "meoh", "etoh", "water", "h2o",
                "hydroxide", "naoh",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.ELECTROPHILIC_AROMATIC_SUBSTITUTION,
            description="Aromatic H replaced by an electrophile; aromaticity restored.",
            reactant_smarts=["c1ccccc1", "[cH]"],
            product_smarts=["c"],
            formed_any=[("C", "C"), ("C", "N"), ("C", "O"), ("C", "X")],
            delta_unsaturation=0,
            reagent_hints=[
                "hno3", "h2so4", "br2", "febr3", "cl2", "alcl3", "so3",
                "rcl", "acyl", "nitration", "halogenation",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.OXIDATION,
            description="Oxidation (e.g. alcohol -> carbonyl / carboxylic acid).",
            reactant_smarts=["[CX4][OX2H1]", "[CX3H1]=O"],
            product_smarts=["[CX3]=[OX1]"],
            formed_any=[("C", "O")],
            delta_unsaturation=1,
            reagent_hints=[
                "pcc", "k2cr2o7", "cro3", "kmno4", "jones", "dess-martin",
                "dmp", "oxidation", "[o]",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.REDUCTION,
            description="Reduction (e.g. carbonyl -> alcohol, alkene -> alkane).",
            reactant_smarts=["[CX3]=[OX1]", "[CX3]=[CX3]"],
            product_smarts=["[CX4][OX2H1]", "[CX4]"],
            delta_unsaturation=-1,
            reagent_hints=[
                "nabh4", "lialh4", "h2", "pd", "pt", "ni", "dibal",
                "reduction", "[h]",
            ],
        ),
        MechanismTemplate(
            mechanism_type=T.ACID_BASE,
            description="Proton transfer; connectivity of heavy atoms is unchanged.",
            reactant_smarts=["*"],
            delta_unsaturation=0,
            no_heavy_change=True,
            reagent_hints=["h+", "h3o", "oh-", "acid", "base", "naoh", "hcl", "deprotonat"],
        ),
    ]
