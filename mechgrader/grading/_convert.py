"""Convert MechGrader mechanisms into chem-grader :class:`ReactionGraph`s.

MechGrader stores a mechanism as an ordered list of **steps**, each step being::

    {"reactants": [atom-mapped SMILES],
     "arrows":    [{"from": "atom:i", "to": "bond:i-j", "kind": "curved"}],
     "products":  [atom-mapped SMILES]}

The `chem-grader` prototype instead grades a directed graph whose nodes are
single molecular structures and whose edges are reaction steps. This module is
the bridge between the two shapes. It deliberately does **no** chemistry of its
own: RDKit (through `chem-grader`) does every parse / canonicalisation / atom
count. We only:

* bundle a step's species into one multi-fragment SMILES -- RDKit reads ``A.B``
  as two disconnected fragments, so ``CCBr.[OH-]`` is a legal one-molecule input;
* emit exactly one chem-grader edge per MechGrader step (``reactants -> products``);
* de-duplicate identical bundles so that when a step's products are literally the
  next step's reactants the graph connects, and when reagents/spectators differ
  it doesn't (which is the honest topology);
* strip atom-map numbers before handing SMILES to chem-grader (it identifies
  molecules by InChIKey, which ignores maps) and remap curved-arrow atom indices
  onto chem-grader's canonical atom order so arrow validation stays meaningful.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional

from rdkit import Chem, RDLogger

from chemgrader import ArrowOp, MoleculeNode, ReactionEdge, ReactionGraph
from chemgrader.structure_service import StructureService
from chemgrader.transformation import element_counts

# chem-grader silences info/warning on import; keep parity here for our own parses.
RDLogger.DisableLog("rdApp.info")
RDLogger.DisableLog("rdApp.warning")


class MechanismFormatError(ValueError):
    """Raised when a MechGrader mechanism dict is structurally malformed.

    This is about the *shape* of the submission (missing ``steps``, a step that
    isn't an object, an empty ``reactants`` list, ...), not about chemistry. A
    bad SMILES is reported separately by :func:`find_unparseable` so the grader
    can return a friendly ``valid: false`` instead of raising.
    """


@dataclass
class StepSpec:
    """One mechanism step with its raw (atom-mapped) SMILES and arrows."""

    index: int
    reactants: list[str]
    products: list[str]
    arrows: list[dict]


@dataclass
class MechanismSpec:
    """A parsed, shape-validated mechanism (an ordered list of steps)."""

    steps: list[StepSpec]

    @property
    def final_products(self) -> list[str]:
        return self.steps[-1].products if self.steps else []


# --------------------------------------------------------------------------- #
# 1. shape parsing / validation
# --------------------------------------------------------------------------- #
def parse_mechanism(data: Any) -> MechanismSpec:
    """Validate the *shape* of a MechGrader mechanism and return a MechanismSpec.

    Accepts either a dict or a JSON string. Raises :class:`MechanismFormatError`
    (never an opaque ``KeyError``/``TypeError``) on malformed input so callers
    can turn it into a friendly message.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise MechanismFormatError("mechanism is not valid JSON") from exc
    if not isinstance(data, dict):
        raise MechanismFormatError("mechanism must be an object with a 'steps' list")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise MechanismFormatError("mechanism must contain a non-empty 'steps' list")

    parsed: list[StepSpec] = []
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise MechanismFormatError(f"step {i + 1} must be an object")
        reactants = _as_smiles_list(raw.get("reactants"), i, "reactants")
        products = _as_smiles_list(raw.get("products"), i, "products")
        arrows = raw.get("arrows") or []
        if not isinstance(arrows, list):
            raise MechanismFormatError(f"step {i + 1}: 'arrows' must be a list")
        parsed.append(StepSpec(index=i, reactants=reactants, products=products, arrows=list(arrows)))
    return MechanismSpec(steps=parsed)


def _as_smiles_list(value: Any, step_index: int, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MechanismFormatError(
            f"step {step_index + 1}: '{field}' must be a non-empty list of SMILES strings"
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise MechanismFormatError(
                f"step {step_index + 1}: '{field}' contains an empty or non-string SMILES"
            )
        out.append(item.strip())
    return out


def find_unparseable(spec: MechanismSpec) -> list[str]:
    """Return friendly descriptions of every SMILES RDKit cannot parse.

    An empty list means all structures are valid molecules. RDKit's parse-error
    chatter is silenced here so a bad submission never dumps a stack-trace-like
    wall of text; we detect failure purely via ``MolFromSmiles(...) is None``.
    """
    bad: list[str] = []
    RDLogger.DisableLog("rdApp.error")
    try:
        for step in spec.steps:
            for role, species in (("reactant", step.reactants), ("product", step.products)):
                for smiles in species:
                    if Chem.MolFromSmiles(smiles) is None:
                        bad.append(f"step {step.index + 1} {role} {smiles!r}")
    finally:
        RDLogger.EnableLog("rdApp.error")
    return bad


# --------------------------------------------------------------------------- #
# 2. bundling + canonicalisation (atom-map aware)
# --------------------------------------------------------------------------- #
def bundle_smiles(species: list[str]) -> str:
    """Join a step's species into one multi-fragment SMILES (``A.B.C``)."""
    return ".".join(species)


def canonical_bundle(species: list[str]) -> tuple[str, dict[int, int]]:
    """Return ``(canonical_smiles, orig_index -> canonical_index)`` for a bundle.

    Atom-map numbers are stripped (chem-grader identifies molecules by InChIKey,
    which ignores them). The index map lets us translate MechGrader arrow atom
    indices -- which are 0-based into the reactant *as listed* -- onto the atom
    order chem-grader will actually see (it re-canonicalises node SMILES before
    validating arrows, and a canonical SMILES re-canonicalises to identity order).
    """
    mol = Chem.MolFromSmiles(bundle_smiles(species))
    if mol is None:
        # Callers validate first via find_unparseable(); this guards direct use.
        raise MechanismFormatError(f"could not parse bundle {bundle_smiles(species)!r}")
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    canonical = Chem.MolToSmiles(mol)
    order = _output_order(mol)
    orig_to_canonical = {orig: pos for pos, orig in enumerate(order)}
    return canonical, orig_to_canonical


def _output_order(mol: Chem.Mol) -> list[int]:
    """Parse RDKit's ``_smilesAtomOutputOrder`` (e.g. ``"[1,2,3,0]"``)."""
    try:
        raw = mol.GetProp("_smilesAtomOutputOrder")
    except KeyError:  # pragma: no cover - defensive; always set after MolToSmiles
        return list(range(mol.GetNumAtoms()))
    inner = raw.strip().strip("[]")
    return [int(tok) for tok in inner.split(",") if tok.strip() != ""]


# --------------------------------------------------------------------------- #
# 3. arrow conversion (MechGrader from/to/kind -> chem-grader ArrowOp)
# --------------------------------------------------------------------------- #
def convert_arrows(arrows: list[dict], orig_to_canonical: dict[int, int]) -> list[ArrowOp]:
    ops: list[ArrowOp] = []
    for arrow in arrows:
        if not isinstance(arrow, dict):
            continue
        source = _remap_endpoint(str(arrow.get("from", "")), orig_to_canonical)
        target = _remap_endpoint(str(arrow.get("to", "")), orig_to_canonical)
        kind = str(arrow.get("kind", "curved")).strip().lower()
        electrons = 1 if kind in {"fishhook", "radical", "single"} else 2
        ops.append(ArrowOp(source=source, target=target, electrons=electrons))
    return ops


def _remap_endpoint(text: str, orig_to_canonical: dict[int, int]) -> str:
    """Remap the atom indices in an ``atom:i`` / ``bond:i-j`` / ``lp:i`` endpoint.

    Malformed endpoints are passed through unchanged so chem-grader's own arrow
    validator reports them (we don't want to silently "fix" a student's error).
    """
    if ":" not in text:
        return text
    kind, rest = text.split(":", 1)
    kind = kind.strip().lower()
    remapped: list[str] = []
    for token in rest.replace("_", "-").split("-"):
        token = token.strip()
        if token == "":
            continue
        try:
            original = int(token)
        except ValueError:
            return text  # let chem-grader flag the malformed endpoint
        remapped.append(str(orig_to_canonical.get(original, original)))
    return f"{kind}:" + "-".join(remapped)


# --------------------------------------------------------------------------- #
# 4. graph construction
# --------------------------------------------------------------------------- #
def build_reaction_graph(spec: MechanismSpec, title: str) -> ReactionGraph:
    """Build a chem-grader :class:`ReactionGraph`: one edge per step.

    Nodes are de-duplicated by canonical bundle SMILES, so identical molecular
    states across steps collapse to one node (connecting the graph exactly when
    a step's products really are the next step's reactants).
    """
    id_by_canonical: dict[str, str] = {}
    nodes: list[MoleculeNode] = []
    edges: list[ReactionEdge] = []

    def ensure_node(species: list[str]) -> tuple[str, dict[int, int]]:
        canonical, orig_to_canonical = canonical_bundle(species)
        node_id = id_by_canonical.get(canonical)
        if node_id is None:
            node_id = f"n{len(nodes)}"
            id_by_canonical[canonical] = node_id
            nodes.append(MoleculeNode(id=node_id, smiles=canonical))
        return node_id, orig_to_canonical

    for step in spec.steps:
        source_id, source_map = ensure_node(step.reactants)
        target_id, _ = ensure_node(step.products)
        edges.append(
            ReactionEdge(
                id=f"e{step.index}",
                source=source_id,
                target=target_id,
                arrows=convert_arrows(step.arrows, source_map),
            )
        )
    return ReactionGraph(title=title, nodes=nodes, edges=edges)


# --------------------------------------------------------------------------- #
# 5. conservation + identity helpers (full element+charge ledger)
# --------------------------------------------------------------------------- #
def step_balance(step: StepSpec) -> tuple[bool, str]:
    """Exact atom + formal-charge balance for one step.

    MechGrader steps carry *every* species (nucleophile, leaving group, proton
    source...), so unlike chem-grader's reactant->product-only edges we really
    can mass-balance. Returns ``(ok, detail)`` where ``detail`` describes the
    imbalance when ``ok`` is ``False``.
    """
    reactant_atoms = _sum_elements(step.reactants)
    product_atoms = _sum_elements(step.products)
    reactant_charge = _sum_charge(step.reactants)
    product_charge = _sum_charge(step.products)

    atoms_ok = reactant_atoms == product_atoms
    charge_ok = reactant_charge == product_charge
    if atoms_ok and charge_ok:
        return True, ""

    parts: list[str] = []
    if not atoms_ok:
        parts.append("atoms " + _format_delta(reactant_atoms, product_atoms))
    if not charge_ok:
        parts.append(f"charge {reactant_charge:+d} -> {product_charge:+d}")
    return False, "; ".join(parts)


def _sum_elements(species: list[str]) -> dict[str, int]:
    counts: Counter = Counter()
    for smiles in species:
        counts.update(element_counts(_require_mol(smiles)))
    return dict(counts)


def _sum_charge(species: list[str]) -> int:
    return sum(Chem.GetFormalCharge(_require_mol(smiles)) for smiles in species)


def _format_delta(reactant_atoms: dict[str, int], product_atoms: dict[str, int]) -> str:
    diffs: list[str] = []
    for element in sorted(set(reactant_atoms) | set(product_atoms)):
        delta = product_atoms.get(element, 0) - reactant_atoms.get(element, 0)
        if delta:
            diffs.append(f"{element}{delta:+d}")
    return "(" + ", ".join(diffs) + ")" if diffs else "(balanced)"


def species_multiset_keys(species: list[str], service: StructureService) -> list[str]:
    """Sorted InChIKeys (map-stripped) for a set of species -- an order- and
    label-independent fingerprint used to compare final products."""
    keys: list[str] = []
    for smiles in species:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            keys.append(f"UNPARSEABLE:{smiles}")
            continue
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(0)
        try:
            keys.append(service.inchikey(mol))
        except Exception:  # pragma: no cover - InChI can fail on exotic inputs
            keys.append("SMILES:" + Chem.MolToSmiles(mol))
    return sorted(keys)


def _require_mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise MechanismFormatError(f"could not parse SMILES {smiles!r}")
    return mol
