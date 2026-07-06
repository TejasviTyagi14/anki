from chemgrader.transformation import analyze_transformation


def bond_strs(bonds):
    return {str(b) for b in bonds}


def test_substitution_breaks_and_forms():
    d = analyze_transformation("CCBr", "CCO")
    assert "Br-C" in bond_strs(d.bonds_broken)
    assert "C-O" in bond_strs(d.bonds_formed)
    assert d.delta_unsaturation == 0
    assert d.charge_balanced


def test_elimination_makes_pi_bond():
    d = analyze_transformation("CCBr", "C=C")
    assert "Br-C" in bond_strs(d.bonds_broken)
    assert d.delta_unsaturation == 1
    assert any(after.order == 2 for _, after in d.order_changes)


def test_carbonyl_addition_lowers_unsaturation():
    d = analyze_transformation("CC=O", "CCO")
    assert d.delta_unsaturation == -1


def test_charge_delta_detected():
    d = analyze_transformation("CC(=O)O", "CC(=O)[O-]")
    assert d.charge_delta == -1
    assert not d.charge_balanced


def test_conservation_flags_unexplained_carbon_gain():
    # product gained a carbon but reagent (water) can't supply one
    d = analyze_transformation("CCO", "CCCO")
    errors = d.conservation_errors(reagents=["H2O"])
    assert errors and "carbon" in errors[0].lower()


def test_conservation_allows_carbon_gain_with_carbon_reagent():
    d = analyze_transformation("CC=O", "CC(O)C")  # +CH3 from a methyl source
    assert d.conservation_errors(reagents=["CH3MgBr (Grignard)"]) == []


def test_conservation_flags_carbon_loss():
    d = analyze_transformation("CCCO", "CCO")
    errors = d.conservation_errors(reagents=["heat"])
    assert errors and "lost" in errors[0].lower()


def test_isomerization_is_balanced():
    d = analyze_transformation("CC(=O)C", "CC(O)=C")
    assert d.is_isomerization
