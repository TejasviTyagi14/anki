from fastapi.testclient import TestClient

from chemgrader.api import create_app

client = TestClient(create_app())


def test_root_serves_editor():
    # The root now serves the MechGrader editor (same-origin as the grader);
    # the endpoint listing moved to /api.
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_api_lists_endpoints():
    r = client.get("/api")
    assert r.status_code == 200
    assert "POST /grade" in r.json()["endpoints"]


def test_canonical_endpoint():
    r = client.post("/structure/canonical", json={"smiles": "OCC"})
    assert r.status_code == 200
    body = r.json()
    assert body["formula"] == "C2H6O"
    assert body["iupac_name"] == "ethanol"
    assert len(body["inchikey"]) == 27


def test_canonical_rejects_bad_smiles():
    r = client.post("/structure/canonical", json={"smiles": "nope!!"})
    assert r.status_code == 400


def test_mechanisms_endpoint():
    r = client.get("/mechanisms")
    assert r.status_code == 200
    types = {m["mechanism_type"] for m in r.json()}
    assert "SN2" in types and "E2" in types


def test_from_input_ocr_stub():
    r = client.post(
        "/structure/from-input",
        json={"source": "ocr", "payload": {"label": "tert-butyl bromide"}},
    )
    assert r.status_code == 200
    assert r.json()["smiles"] == "CC(C)(C)Br"


def _molblock(atoms, bonds):
    # mirrors the frontend Sketcher.toMolblock format (x/40, -y/40 coords)
    pad3 = lambda n: str(n).rjust(3)  # noqa: E731
    f10 = lambda v: format(v, ".4f").rjust(10)  # noqa: E731
    lines = ["", "  chemgrader", "",
             pad3(len(atoms)) + pad3(len(bonds)) + "  0  0  0  0  0  0  0  0999 V2000"]
    for el, x, y in atoms:
        lines.append(f10(x / 40) + f10(-y / 40) + f10(0) + " " + el.ljust(3) +
                     " 0  0  0  0  0  0  0  0  0  0  0  0")
    for a, b, o in bonds:
        lines.append(pad3(a) + pad3(b) + pad3(o) + pad3(0))
    lines.append("M  END")
    return "\n".join(lines) + "\n"


def test_from_input_molblock_from_sketcher():
    # a drawn C-O skeleton should become methanol (implicit H filled by RDKit)
    mb = _molblock([("C", 0, 0), ("O", 40, 0)], [(1, 2, 1)])
    r = client.post("/structure/from-input", json={"source": "molblock", "payload": {"molblock": mb}})
    assert r.status_code == 200
    assert r.json()["smiles"] == "CO"


def test_reference_then_grade_by_id():
    ref = {
        "nodes": [
            {"id": "a", "smiles": "CCBr"},
            {"id": "b", "smiles": "CCO"},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "b", "reagents": ["NaOH"], "mechanism_type": "SN2"}
        ],
    }
    rid = client.post("/reference", json=ref).json()["id"]

    grade_req = {"reference_id": rid, "attempt": ref}
    r = client.post("/grade", json=grade_req)
    assert r.status_code == 200
    result = r.json()
    assert result["passed"] is True
    assert result["overall_score"] >= 0.95


def test_grade_requires_reference():
    r = client.post("/grade", json={"attempt": {"nodes": [{"id": "a", "smiles": "CCO"}]}})
    assert r.status_code == 400


def test_frontend_served_from_backend():
    # the UI is mounted at /app so the whole thing runs on one port
    r = client.get("/app/")
    assert r.status_code == 200
    assert "Reaction Mechanism Grader" in r.text


def test_list_problems_covers_four_mechanisms_and_hides_answers():
    r = client.get("/problems")
    assert r.status_code == 200
    probs = r.json()
    assert len(probs) >= 6
    assert {"SN1", "SN2", "E1", "E2"} <= {p["mechanism"] for p in probs}
    for p in probs:  # the answer must never be sent to the client
        assert "products" not in p
        assert "answer" not in p


def test_problem_grade_correct_product_and_mechanism():
    r = client.post(
        "/problems/sn1-1/grade",
        json={"product_smiles": "CC(C)(C)O", "mechanism_type": "SN1"},
    )
    assert r.status_code == 200
    assert r.json()["passed"] is True


def test_problem_grade_right_product_wrong_mechanism():
    r = client.post(
        "/problems/sn1-1/grade",
        json={"product_smiles": "CC(C)(C)O", "mechanism_type": "SN2"},
    )
    body = r.json()
    assert body["passed"] is False
    assert any("mechanism" in h.lower() for h in body["hints"])


def test_problem_grade_wrong_product():
    r = client.post(
        "/problems/sn1-1/grade",
        json={"product_smiles": "CCO", "mechanism_type": "SN1"},
    )
    assert r.json()["passed"] is False


def test_problem_not_found():
    r = client.post("/problems/nope/grade", json={"product_smiles": "CCO"})
    assert r.status_code == 404


def test_structure_svg_renders():
    r = client.post("/structure/svg", json={"smiles": "c1ccccc1"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in r.text


def test_structure_svg_with_highlight():
    r = client.post("/structure/svg", json={"smiles": "CCO", "highlight_atoms": [2], "highlight_bonds": [[1, 2]]})
    assert r.status_code == 200 and "<svg" in r.text


def test_structure_diff_same_molecule():
    r = client.post("/structure/diff", json={"a": "CCO", "b": "OCC"})
    assert r.json()["same"] is True


def test_structure_diff_reports_differences():
    r = client.post("/structure/diff", json={"a": "CCO", "b": "CCC"})
    d = r.json()
    assert d["same"] is False
    assert d["changed_atoms_a"] or d["changed_atoms_b"]


def test_problem_answer_reveal():
    r = client.get("/problems/sn1-1/answer")
    assert r.status_code == 200
    body = r.json()
    assert body["mechanism"] == "SN1"
    assert isinstance(body["products"], list) and body["products"]
