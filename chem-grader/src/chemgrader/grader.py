"""The layered grader.

Runs five checks and folds them into a :class:`~chemgrader.feedback.GradeResult`:

1. **Node correctness** -- do the attempt's structures match the reference
   (by InChIKey, under the active tolerance flags)?
2. **Transformation validity** -- for each edge, is source->product chemically
   plausible (atom mapping exists, atoms/charge conserved, what changed)?
3. **Mechanism correctness** -- does the stated mechanism type + reagents match a
   transformation that could produce the observed change (rule library)?
4. **Arrow-pushing** -- if provided, is the electron flow consistent and legal?
5. **Path-level grading** -- align the attempt to the reference graph, tolerate
   valid alternative routes to the same product, and score partial credit.

Every heuristic that could produce a false positive/negative is annotated in the
relevant module and summarised in the README.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .arrows import validate_arrows
from .feedback import (
    EdgeFeedback,
    GradeResult,
    NodeFeedback,
    NodeStatus,
    ScoreBreakdown,
)
from .graph_align import Alignment, align
from .mechanisms import MechanismRuleLibrary
from .models import ComparisonOptions, ReactionGraph
from .structure_service import StructureError, StructureService
from .transformation import TransformationDiff, analyze_transformation


class GraderConfig(BaseModel):
    comparison: ComparisonOptions = Field(default_factory=ComparisonOptions)
    # weights (should sum to ~1)
    w_nodes: float = 0.30
    w_transformations: float = 0.30
    w_mechanisms: float = 0.25
    w_pathway: float = 0.15
    # a step whose reactant/product share less than this fraction of atoms is
    # flagged as possibly-more-than-one-step (see transformation.py caveats).
    min_mcs_coverage: float = 0.5
    pass_threshold: float = 0.7
    require_arrows: bool = False
    wrong_node_penalty: float = 0.1


class Grader:
    def __init__(
        self,
        service: Optional[StructureService] = None,
        library: Optional[MechanismRuleLibrary] = None,
        name_resolver=None,
    ):
        self.service = service or StructureService()
        self.library = library or MechanismRuleLibrary()
        self.name_resolver = name_resolver  # display-only; never gates grading

    # ------------------------------------------------------------------ #
    def grade(
        self,
        reference: ReactionGraph,
        attempt: ReactionGraph,
        config: Optional[GraderConfig] = None,
    ) -> GradeResult:
        config = config or GraderConfig()
        reference = self._enriched(reference)
        attempt = self._enriched(attempt)

        alignment = align(reference, attempt, self.service, config.comparison)
        edge_fbs = self._grade_edges(attempt, alignment, config)
        node_fbs = self._grade_nodes(reference, attempt, alignment, edge_fbs)
        return self._aggregate(reference, attempt, alignment, node_fbs, edge_fbs, config)

    # ------------------------------------------------------------------ #
    def _enriched(self, graph: ReactionGraph) -> ReactionGraph:
        g = graph.model_copy(deep=True)
        for node in g.nodes:
            self.service.enrich(node, self.name_resolver)
        return g

    # ---- edges -------------------------------------------------------- #
    def _grade_edges(
        self, attempt: ReactionGraph, alignment: Alignment, config: GraderConfig
    ) -> list[EdgeFeedback]:
        node_map = attempt.node_map()
        out: list[EdgeFeedback] = []
        for edge in attempt.edges:
            fb = self._grade_edge(
                edge, node_map.get(edge.source), node_map.get(edge.target), config
            )
            fb.matches_reference = alignment.edge_matches.get(edge.id, False)
            out.append(fb)
        return out

    def _grade_edge(self, edge, src, tgt, config: GraderConfig) -> EdgeFeedback:
        fb = EdgeFeedback(
            edge_id=edge.id,
            source=edge.source,
            target=edge.target,
            mechanism_stated=edge.mechanism_type,
        )
        if src is None or tgt is None:
            fb.transformation_plausible = False
            fb.conservation_ok = False
            fb.errors.append("edge references a missing node")
            fb.score = 0.0
            return fb
        if src.error or tgt.error:
            fb.transformation_plausible = False
            fb.conservation_ok = False
            fb.errors.append("cannot analyze step: an endpoint structure is invalid")
            fb.score = 0.0
            return fb

        try:
            diff = analyze_transformation(src.canonical_smiles, tgt.canonical_smiles)
        except StructureError as exc:
            fb.transformation_plausible = False
            fb.errors.append(str(exc))
            fb.score = 0.0
            return fb

        fb.changes = diff.describe()

        # --- conservation ---
        cons_errors = diff.conservation_errors(edge.reagents)
        if cons_errors:
            fb.conservation_ok = False
            fb.errors.extend(cons_errors)
        if not diff.charge_balanced:
            fb.warnings.append(
                f"net charge changes by {diff.charge_delta:+d} on this step "
                "(fine for ionization/acid-base; otherwise double-check)"
            )

        # --- transformation plausibility ---
        low_overlap = (not diff.mapped) or diff.mcs_coverage < config.min_mcs_coverage
        if low_overlap:
            fb.warnings.append(
                f"reactant and product share little structure (atom-map coverage "
                f"{diff.mcs_coverage:.0%}); this may be more than one elementary step"
            )
        if not diff.describe():
            fb.warnings.append("no structural change detected between these two structures")
        fb.transformation_plausible = fb.conservation_ok and not low_overlap

        # --- mechanism ---
        reactant = self.service.try_parse(src.canonical_smiles)
        product = self.service.try_parse(tgt.canonical_smiles)
        mech_score = self._grade_mechanism(edge, diff, reactant, product, fb)

        # --- arrows ---
        self._grade_arrows(edge, reactant, diff, fb, config)

        trans_part = 1.0 if fb.transformation_plausible else 0.0
        cons_part = 1.0 if fb.conservation_ok else 0.0
        fb.score = round(0.45 * trans_part + 0.35 * mech_score + 0.20 * cons_part, 4)
        return fb

    def _grade_mechanism(self, edge, diff: TransformationDiff, reactant, product, fb) -> float:
        if reactant is None or product is None:
            return 0.5
        inferred = self.library.infer(diff, reactant, product, edge.reagents)
        top = inferred[0] if inferred else None

        if not edge.mechanism_type:
            fb.mechanism_consistent = None
            if top:
                fb.hints.append(
                    f"no mechanism stated; the change is consistent with "
                    f"{top.mechanism_type.value}"
                )
                return 0.5
            return 0.3

        template = self.library.get(edge.mechanism_type)
        if template is None:
            fb.mechanism_consistent = None
            fb.warnings.append(f"unknown mechanism type {edge.mechanism_type!r}; not checked")
            return 0.4

        ev = self.library.evaluate(template, diff, reactant, product, edge.reagents)
        fb.mechanism_consistent = ev.consistent
        fb.reagents_ok = ev.reagent_ok
        fb.warnings.extend(ev.substrate_warnings)
        if ev.reagent_ok is False:
            fb.warnings.append(
                f"reagents don't look typical for {template.mechanism_type.value}"
            )

        if ev.consistent:
            score = 1.0
            if ev.substrate_warnings:
                score -= 0.3
            if ev.reagent_ok is False:
                score -= 0.1
            return max(0.0, score)

        fb.errors.append(
            f"stated mechanism {template.mechanism_type.value} is inconsistent with "
            "the observed structural change"
        )
        if not ev.reactant_ok:
            fb.errors.append(
                f"reactant lacks the functional group {template.mechanism_type.value} acts on"
            )
        if top and top.mechanism_type != template.mechanism_type:
            fb.hints.append(f"the observed change looks more like {top.mechanism_type.value}")
        return 0.0

    def _grade_arrows(self, edge, reactant, diff, fb, config: GraderConfig) -> None:
        if edge.arrows:
            report = validate_arrows(edge.arrows, reactant, diff)
            fb.arrows_checked = report.checked
            fb.arrows_ok = report.ok
            fb.errors.extend(report.errors)
            fb.warnings.extend(report.warnings)
        elif config.require_arrows:
            fb.warnings.append("no arrow-pushing provided for this step")

    # ---- nodes -------------------------------------------------------- #
    def _grade_nodes(
        self, reference, attempt, alignment: Alignment, edge_fbs
    ) -> list[NodeFeedback]:
        incident: dict[str, list[EdgeFeedback]] = {n.id: [] for n in attempt.nodes}
        fb_by_edge = {fb.edge_id: fb for fb in edge_fbs}
        for e in attempt.edges:
            for nid in (e.source, e.target):
                if nid in incident:
                    incident[nid].append(fb_by_edge[e.id])

        start = set(reference.start_nodes())
        end = set(reference.end_nodes())

        out: list[NodeFeedback] = []
        for n in attempt.nodes:
            if n.error:
                status, msg = NodeStatus.INVALID, n.error or "invalid structure"
            elif alignment.node_match.get(n.id):
                status, msg = NodeStatus.CORRECT, "matches a reference structure"
            else:
                inc = incident.get(n.id, [])
                if not inc:
                    status = NodeStatus.EXTRANEOUS
                    msg = "structure isn't connected to any reaction step"
                elif any(f.transformation_plausible for f in inc) and alignment.reproduced_products:
                    status = NodeStatus.VALID_ALTERNATIVE
                    msg = "not in the reference, but a plausible intermediate on your route"
                else:
                    status = NodeStatus.WRONG
                    msg = "doesn't match the reference and isn't a plausible intermediate"
            out.append(
                NodeFeedback(
                    node_id=n.id,
                    status=status,
                    smiles=n.canonical_smiles or n.smiles,
                    inchikey=n.inchikey,
                    iupac_name=n.iupac_name,
                    message=msg,
                )
            )

        for nid in alignment.missing_reference:
            is_intermediate = nid not in start and nid not in end
            if is_intermediate and alignment.reference_products_reached:
                continue  # bypassed by a valid alternative route -- not penalised
            rn = reference.node(nid)
            out.append(
                NodeFeedback(
                    node_id=f"ref:{nid}",
                    status=NodeStatus.MISSING,
                    smiles=rn.canonical_smiles or rn.smiles,
                    inchikey=rn.inchikey,
                    iupac_name=rn.iupac_name,
                    message="reference structure not reproduced in your attempt",
                )
            )
        return out

    # ---- aggregate ---------------------------------------------------- #
    def _aggregate(
        self, reference, attempt, alignment: Alignment, node_fbs, edge_fbs, config
    ) -> GradeResult:
        start = set(reference.start_nodes())
        end = set(reference.end_nodes())

        counted: list[float] = []
        for n in reference.nodes:
            matched = n.id in alignment.matched_reference
            is_intermediate = n.id not in start and n.id not in end
            if not matched and is_intermediate and alignment.reference_products_reached:
                continue  # bypassed intermediate; don't penalise alternative routes
            counted.append(1.0 if matched else 0.0)
        nodes_score = sum(counted) / len(counted) if counted else 1.0
        num_wrong = sum(1 for fb in node_fbs if fb.status == NodeStatus.WRONG)

        if edge_fbs:
            transformations_score = sum(
                1.0 if fb.transformation_plausible else 0.0 for fb in edge_fbs
            ) / len(edge_fbs)
            mech_vals = []
            for fb in edge_fbs:
                if fb.mechanism_consistent is True:
                    mech_vals.append(1.0)
                elif fb.mechanism_consistent is False:
                    mech_vals.append(0.0)
                else:
                    mech_vals.append(0.5)
            mechanisms_score = sum(mech_vals) / len(mech_vals)
        else:
            transformations_score = 1.0 if not reference.edges else 0.0
            mechanisms_score = 1.0 if not reference.edges else 0.0

        ref_end_keys = alignment.reference_end_keys
        product_fraction = (
            len(alignment.reproduced_products) / len(ref_end_keys) if ref_end_keys else 1.0
        )
        pathway_score = product_fraction * (
            1.0 if alignment.reference_products_reached else 0.6
        )

        overall = (
            config.w_nodes * nodes_score
            + config.w_transformations * transformations_score
            + config.w_mechanisms * mechanisms_score
            + config.w_pathway * pathway_score
        )
        if num_wrong:
            overall *= max(0.0, 1.0 - config.wrong_node_penalty * num_wrong)

        all_products = bool(ref_end_keys) and alignment.reproduced_products == ref_end_keys
        passed = overall >= config.pass_threshold and all_products

        breakdown = ScoreBreakdown(
            nodes=round(nodes_score, 4),
            transformations=round(transformations_score, 4),
            mechanisms=round(mechanisms_score, 4),
            pathway=round(pathway_score, 4),
        )
        summary, hints = self._summarise(
            alignment, node_fbs, edge_fbs, all_products, passed
        )
        return GradeResult(
            overall_score=round(overall, 4),
            passed=passed,
            summary=summary,
            breakdown=breakdown,
            nodes=node_fbs,
            edges=edge_fbs,
            hints=hints,
        )

    def _summarise(self, alignment, node_fbs, edge_fbs, all_products, passed):
        hints: list[str] = []
        used_alt = any(fb.status == NodeStatus.VALID_ALTERNATIVE for fb in node_fbs)
        missing = [fb for fb in node_fbs if fb.status == NodeStatus.MISSING]
        wrong = [fb for fb in node_fbs if fb.status == NodeStatus.WRONG]
        mech_errors = sum(1 for fb in edge_fbs if fb.mechanism_consistent is False)
        cons_errors = sum(1 for fb in edge_fbs if not fb.conservation_ok)

        if not all_products:
            summary = "The final product does not match the reference."
            hints.append("Check your final step(s): the target product wasn't reproduced.")
        elif passed:
            summary = "Correct: you reached the target product."
            if used_alt:
                summary += " (via a valid alternative route)"
        else:
            summary = "Right product, but some steps have problems."

        if used_alt and all_products:
            hints.append(
                "You reached the correct product by a different route than the "
                "reference -- accepted."
            )
        if missing:
            hints.append(f"{len(missing)} reference structure(s) not reproduced.")
        if wrong:
            hints.append(f"{len(wrong)} structure(s) don't belong in this mechanism.")
        if mech_errors:
            hints.append(
                f"{mech_errors} step(s) state a mechanism inconsistent with the "
                "structural change."
            )
        if cons_errors:
            hints.append(f"{cons_errors} step(s) don't conserve atoms.")
        return summary, hints
