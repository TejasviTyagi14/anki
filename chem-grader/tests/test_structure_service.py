from chemgrader import ComparisonOptions, MockNameResolver, MoleculeNode, StructureService

svc = StructureService()


def test_canonicalization_is_order_independent():
    assert svc.canonical_smiles("OCC") == svc.canonical_smiles("CCO")


def test_inchikey_identifies_same_molecule():
    assert svc.inchikey("OCC") == svc.inchikey("CCO")
    assert svc.inchikey("CCO") != svc.inchikey("CCC")


def test_identity_fields():
    ident = svc.identity("CC(=O)O")
    assert ident.formula == "C2H4O2"
    assert ident.mol_weight > 59 and ident.mol_weight < 61
    assert "carboxylic_acid" in ident.functional_groups
    assert len(ident.inchikey) == 27  # standard InChIKey length


def test_enrich_populates_node_and_uses_name_resolver():
    node = MoleculeNode(id="n", smiles="CCO")
    svc.enrich(node, MockNameResolver())
    assert node.inchikey == svc.inchikey("CCO")
    assert node.formula == "C2H6O"
    assert node.iupac_name == "ethanol"  # display-only
    assert node.error is None


def test_enrich_bad_smiles_sets_error_not_exception():
    node = MoleculeNode(id="bad", smiles="this-is-not-smiles")
    svc.enrich(node)
    assert node.error is not None
    assert node.inchikey is None


def test_stereochemistry_tolerance_toggle():
    r = "CC[C@H](C)O"
    s = "CC[C@@H](C)O"
    assert not svc.same_molecule(r, s)  # strict: enantiomers differ
    assert svc.same_molecule(r, s, ComparisonOptions(ignore_stereo=True))


def test_charge_tolerance_toggle():
    acid = "CC(=O)O"
    conjugate_base = "CC(=O)[O-]"
    assert not svc.same_molecule(acid, conjugate_base)
    assert svc.same_molecule(acid, conjugate_base, ComparisonOptions(ignore_charge=True))


def test_tautomer_tolerance_toggle():
    keto = "CC(=O)C"
    enol = "CC(O)=C"
    assert svc.same_molecule(keto, enol, ComparisonOptions(allow_tautomers=True))
