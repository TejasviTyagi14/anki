from rdkit import Chem

from chemgrader.functional_groups import detect_functional_groups


def fgs(smiles):
    return set(detect_functional_groups(Chem.MolFromSmiles(smiles)))


def test_alcohol_classes():
    assert "primary_alcohol" in fgs("CCO")
    assert "tertiary_alcohol" in fgs("CC(C)(C)O")


def test_carbonyls():
    assert "ketone" in fgs("CC(=O)C")
    assert "aldehyde" in fgs("CC=O")
    assert "carboxylic_acid" in fgs("CC(=O)O")
    assert "ester" in fgs("CC(=O)OC")


def test_halides_and_unsaturation():
    assert "alkyl_halide" in fgs("CCBr")
    assert "alkene" in fgs("C=CC")
    assert "alkyne" in fgs("C#CC")
    assert "aromatic_ring" in fgs("c1ccccc1")


def test_nitrogen_groups():
    assert "primary_amine" in fgs("CCN")
    assert "amide" in fgs("CC(N)=O")
    assert "nitrile" in fgs("CC#N")


def test_empty_for_alkane():
    assert fgs("CCC") == set()
