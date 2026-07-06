/*
 * flashcard-grader.js — turn the editor's `mol` into the grading payload,
 * rasterize the canvas to PNG, and send both to the backend proxy (which holds
 * the company OpenAI key). Exposes window.Grader.
 *
 * Depends on window.Chem (chem.js).
 */
(function () {
  "use strict";

  const W = 960;
  const H = 560;
  const R = Math.round;

  /**
   * Build the machine-readable submission from the editor's mol. This is the
   * single place ids are remapped to indices for chem.js.
   */
  function buildSubmission(mol) {
    const Chem = window.Chem;
    const atoms = mol.atoms || [];
    const idToIndex = new Map();
    atoms.forEach((a, i) => idToIndex.set(a.id, i));

    const idxAtoms = atoms.map((a) => ({ el: a.el, charge: a.charge || 0, x: a.x, y: a.y }));
    const idxBonds = (mol.bonds || [])
      .filter((b) => idToIndex.has(b.a) && idToIndex.has(b.b))
      .map((b) => ({ a: idToIndex.get(b.a), b: idToIndex.get(b.b), order: b.order || 1, style: b.style || "plain" }));

    // arrows sorted left-to-right, numbered 1..n
    const sortedArrows = (mol.arrows || [])
      .slice()
      .sort((p, q) => (p.x1 + p.x2) / 2 - (q.x1 + q.x2) / 2);
    const arrows = sortedArrows.map((ar, i) => ({
      n: i + 1,
      x1: R(ar.x1),
      y1: R(ar.y1),
      x2: R(ar.x2),
      y2: R(ar.y2),
    }));
    const arrowMidX = sortedArrows.map((ar) => (ar.x1 + ar.x2) / 2);
    const arrowMidY = sortedArrows.map((ar) => (ar.y1 + ar.y2) / 2);

    const comps = Chem.connectedComponents(idxAtoms, idxBonds);
    const molecules = comps.map((comp) => {
      const local = new Map();
      comp.forEach((gi, li) => local.set(gi, li));
      const localAtoms = comp.map((gi) => idxAtoms[gi]);
      const localBonds = idxBonds
        .filter((b) => local.has(b.a) && local.has(b.b))
        .map((b) => ({ a: local.get(b.a), b: local.get(b.b), order: b.order, style: b.style }));
      const sums = Chem.bondOrderSums(localAtoms, localBonds);

      const atomsOut = comp.map((gi, li) => ({
        i: li,
        element: localAtoms[li].el,
        charge: localAtoms[li].charge,
        x: R(localAtoms[li].x),
        y: R(localAtoms[li].y),
        implicit_h: Chem.implicitHydrogens(localAtoms[li], sums[li]),
      }));
      const bondsOut = localBonds.map((b) => ({ from: b.a, to: b.b, order: b.order, stereo: b.style }));

      const cx = localAtoms.reduce((s, a) => s + a.x, 0) / (localAtoms.length || 1);
      let role;
      if (arrows.length === 0) {
        role = "structure";
      } else {
        const leftCount = arrowMidX.filter((m) => m < cx).length;
        if (leftCount === 0) role = "reactant";
        else if (leftCount === arrows.length) role = "product";
        else role = `intermediate_after_arrow_${leftCount}`;
      }

      return {
        role,
        formula: Chem.moleculeFormula(localAtoms, localBonds),
        smiles: Chem.moleculeToSmiles(localAtoms, localBonds),
        atoms: atomsOut,
        bonds: bondsOut,
      };
    });

    // labels: link each text to an arrow it sits over/under
    const labels = (mol.texts || []).map((t) => {
      let linked = null;
      let position = null;
      for (let i = 0; i < sortedArrows.length; i++) {
        const ar = sortedArrows[i];
        const lo = Math.min(ar.x1, ar.x2) - 30;
        const hi = Math.max(ar.x1, ar.x2) + 30;
        if (t.x >= lo && t.x <= hi && Math.abs(t.y - arrowMidY[i]) < 60) {
          linked = i + 1;
          position = t.y < arrowMidY[i] ? "above_arrow" : "below_arrow";
          break;
        }
      }
      return { text: t.str, arrow: linked, position };
    });

    return {
      canvas: { width: W, height: H, note: "y increases downward" },
      arrows,
      labels,
      molecules,
    };
  }

  /** A short human-readable SMILES readout grouped by reactants -> products. */
  function smilesReadout(payload) {
    const mols = payload.molecules || [];
    if (!mols.length) return "—";
    if (!payload.arrows || !payload.arrows.length) {
      return mols.map((m) => m.smiles).filter(Boolean).join("  ·  ") || "—";
    }
    const reactants = mols.filter((m) => m.role === "reactant").map((m) => m.smiles);
    const products = mols.filter((m) => m.role === "product").map((m) => m.smiles);
    const inter = mols.filter((m) => /intermediate/.test(m.role)).map((m) => m.smiles);
    const left = reactants.join(" + ") || "?";
    const mid = inter.length ? " → " + inter.join(" + ") : "";
    const right = products.length ? " → " + products.join(" + ") : "";
    return (left + mid + right).trim();
  }

  /** SVG -> base64 PNG (no data: prefix), rasterized on a white background at `scale`. */
  function svgToPngBase64(svg, scale) {
    scale = scale || 1.5;
    return new Promise((resolve, reject) => {
      const clone = svg.cloneNode(true);
      clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      clone.setAttribute("width", String(W));
      clone.setAttribute("height", String(H));
      clone.setAttribute("viewBox", `0 0 ${W} ${H}`);
      const str = new XMLSerializer().serializeToString(clone);
      const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(str);
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(W * scale);
        canvas.height = Math.round(H * scale);
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        try {
          resolve(canvas.toDataURL("image/png").split(",")[1]);
        } catch (e) {
          reject(e);
        }
      };
      img.onerror = () => reject(new Error("Could not rasterize the drawing."));
      img.src = url;
    });
  }

  /** POST a grade request to the backend proxy and return the parsed grade. */
  async function postGrade(body) {
    let resp;
    try {
      resp = await fetch("/flashcards/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (e) {
      throw new Error("Could not reach the grader. Is the backend running?");
    }
    if (!resp.ok) {
      let detail = `Grading failed (HTTP ${resp.status}).`;
      try {
        const data = await resp.json();
        if (data && data.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } catch (_) {}
      throw new Error(detail);
    }
    return resp.json();
  }

  /** Grade a STRUCTURED drawing (image + machine-readable graph). */
  async function gradeSubmission({ problemId, statement, mol, svg, hint }) {
    const payload = buildSubmission(mol);
    const image = await svgToPngBase64(svg);
    return postGrade({
      problem_id: problemId || null,
      statement: statement || null,
      image_png_base64: image,
      payload,
      hint: !!hint,
      freehand: false,
    });
  }

  /** Grade a FREEHAND sketch (image only — no machine-readable graph). */
  async function gradeFreehand({ problemId, statement, imageBase64, hint }) {
    return postGrade({
      problem_id: problemId || null,
      statement: statement || null,
      image_png_base64: imageBase64,
      payload: {},
      hint: !!hint,
      freehand: true,
    });
  }

  window.Grader = { buildSubmission, smilesReadout, svgToPngBase64, gradeSubmission, gradeFreehand };
})();
