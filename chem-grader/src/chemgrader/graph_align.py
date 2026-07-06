"""Align an attempt mechanism graph to a reference graph by *identity*.

Nodes are matched on their comparison key (InChIKey under the active tolerance
flags), never on node ids or names. This lets the grader:

* recognise correct intermediates/products even if drawn in a different order,
* tolerate alternative routes that reach the same product,
* detect missing reference structures and extraneous attempt structures.

The alignment is purely structural; deciding whether an unmatched node is a
*valid alternative* vs simply *wrong* also needs transformation validity, so that
final call is made in :mod:`chemgrader.grader`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from .models import ComparisonOptions, ReactionGraph
from .structure_service import StructureService


@dataclass
class Alignment:
    ref_key_by_node: dict[str, Optional[str]]
    att_key_by_node: dict[str, Optional[str]]
    node_match: dict[str, Optional[str]] = field(default_factory=dict)
    matched_reference: set[str] = field(default_factory=set)
    missing_reference: list[str] = field(default_factory=list)
    edge_matches: dict[str, bool] = field(default_factory=dict)
    reference_start_keys: set[str] = field(default_factory=set)
    reference_end_keys: set[str] = field(default_factory=set)
    attempt_keys: set[str] = field(default_factory=set)
    reproduced_products: set[str] = field(default_factory=set)
    reference_products_reached: bool = False


def _keys_for(graph: ReactionGraph, service: StructureService, options: ComparisonOptions):
    keys: dict[str, Optional[str]] = {}
    for node in graph.nodes:
        smiles = node.canonical_smiles or node.smiles
        try:
            keys[node.id] = service.comparison_key(smiles, options)
        except Exception:
            keys[node.id] = None
    return keys


def align(
    reference: ReactionGraph,
    attempt: ReactionGraph,
    service: StructureService,
    options: Optional[ComparisonOptions] = None,
) -> Alignment:
    options = options or ComparisonOptions()
    ref_keys = _keys_for(reference, service, options)
    att_keys = _keys_for(attempt, service, options)

    # index reference nodes by key
    ref_by_key: dict[str, list[str]] = {}
    for nid, key in ref_keys.items():
        if key is not None:
            ref_by_key.setdefault(key, []).append(nid)

    node_match: dict[str, Optional[str]] = {}
    matched_reference: set[str] = set()
    for nid, key in att_keys.items():
        match = None
        if key is not None and key in ref_by_key:
            match = ref_by_key[key][0]
            matched_reference.add(match)
        node_match[nid] = match

    att_key_set = {k for k in att_keys.values() if k is not None}
    missing_reference = [
        nid for nid, key in ref_keys.items() if key is None or key not in att_key_set
    ]

    # edge matching by endpoint identity
    ref_edge_keys = {
        (ref_keys.get(e.source), ref_keys.get(e.target)) for e in reference.edges
    }
    edge_matches: dict[str, bool] = {}
    for e in attempt.edges:
        pair = (att_keys.get(e.source), att_keys.get(e.target))
        edge_matches[e.id] = None not in pair and pair in ref_edge_keys

    reference_start_keys = {
        ref_keys[n] for n in reference.start_nodes() if ref_keys.get(n)
    }
    reference_end_keys = {ref_keys[n] for n in reference.end_nodes() if ref_keys.get(n)}
    reproduced_products = reference_end_keys & att_key_set

    # reachability on the attempt's identity graph
    kg = nx.DiGraph()
    for key in att_key_set:
        kg.add_node(key)
    for e in attempt.edges:
        s, t = att_keys.get(e.source), att_keys.get(e.target)
        if s is not None and t is not None:
            kg.add_edge(s, t)

    reached = bool(reference_end_keys)
    for end_key in reference_end_keys:
        if end_key not in kg:
            reached = False
            break
        starts = [s for s in reference_start_keys if s in kg]
        if not starts:
            # No shared starting material; a lone product node still counts as
            # "reached" only if there are no edges expected at all.
            reached = reached and (end_key in att_key_set and not reference.edges)
            continue
        if not any(nx.has_path(kg, s, end_key) for s in starts):
            reached = False
            break

    return Alignment(
        ref_key_by_node=ref_keys,
        att_key_by_node=att_keys,
        node_match=node_match,
        matched_reference=matched_reference,
        missing_reference=missing_reference,
        edge_matches=edge_matches,
        reference_start_keys=reference_start_keys,
        reference_end_keys=reference_end_keys,
        attempt_keys=att_key_set,
        reproduced_products=reproduced_products,
        reference_products_reached=reached,
    )
