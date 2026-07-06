from rdkit import Chem

from chemgrader.mechanisms import MechanismRuleLibrary, leaving_group_carbon_class
from chemgrader.models import MechanismType
from chemgrader.transformation import analyze_transformation

lib = MechanismRuleLibrary()


def _eval(mech, r, p, reagents):
    diff = analyze_transformation(r, p)
    template = lib.get(mech)
    return lib.evaluate(template, diff, Chem.MolFromSmiles(r), Chem.MolFromSmiles(p), reagents)


def test_library_has_enough_templates():
    assert len(lib.all()) >= 8


def test_sn2_consistent_for_primary_substitution():
    ev = _eval("SN2", "CCBr", "CCO", ["NaOH"])
    assert ev.consistent
    assert not ev.substrate_warnings


def test_sn2_on_tertiary_is_flagged():
    ev = _eval("SN2", "CC(C)(C)Br", "CC(C)(C)O", ["NaOH"])
    assert ev.substrate_warnings  # sterically implausible
    assert "tertiary" in ev.substrate_warnings[0].lower()


def test_sn1_favored_on_tertiary():
    ev = _eval("SN1", "CC(C)(C)Br", "CC(C)(C)O", ["H2O"])
    assert ev.consistent
    assert not ev.substrate_warnings


def test_e2_consistent_but_sn2_not_for_elimination():
    assert _eval("E2", "CCBr", "C=C", ["KOtBu"]).consistent
    assert not _eval("SN2", "CCBr", "C=C", ["KOtBu"]).consistent  # unsaturation changed


def test_nucleophilic_acyl_substitution():
    ev = _eval("nucleophilic_acyl_substitution", "CC(=O)Cl", "CC(N)=O", ["NH3"])
    assert ev.consistent


def test_oxidation_of_alcohol():
    ev = _eval("oxidation", "CCO", "CC=O", ["PCC"])
    assert ev.consistent


def test_leaving_group_carbon_class():
    assert leaving_group_carbon_class(Chem.MolFromSmiles("CBr")) == "methyl"
    assert leaving_group_carbon_class(Chem.MolFromSmiles("CCBr")) == "primary"
    assert leaving_group_carbon_class(Chem.MolFromSmiles("CC(C)(C)Br")) == "tertiary"


def test_infer_prefers_sn1_on_tertiary_in_protic():
    diff = analyze_transformation("CC(C)(C)Br", "CC(C)(C)O")
    ranked = lib.infer(
        diff,
        Chem.MolFromSmiles("CC(C)(C)Br"),
        Chem.MolFromSmiles("CC(C)(C)O"),
        ["H2O", "heat"],
    )
    assert ranked[0].mechanism_type == MechanismType.SN1
