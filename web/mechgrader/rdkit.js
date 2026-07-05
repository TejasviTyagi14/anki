/**
 * rdkit.js — RDKit-JS (WASM) seam + an honest pure-JS fallback for MechGrader.
 *
 * Framework-free ES module. Two paths:
 *
 *   REAL (documented seam, NOT bundled): load @rdkit/rdkit's WASM build from an
 *   OFFLINE MIRROR (no CDN) and use it for canonical SMILES + final-product match.
 *
 *   FALLBACK (active by default): exact/near-string product match. This is
 *   ⚠️ NOT real canonicalization — "CCO" and "OCC" are the same molecule but
 *   compare unequal here. It exists so the bundle runs with zero native deps.
 *   Every fallback result is labeled `canonical:false` and the grade engine is
 *   reported as "fallback-string-match (NOT real canonicalization)".
 *
 * ── HOW TO WIRE REAL RDKIT-JS (offline mirror) ───────────────────────────────
 *   1) Vendor it offline (no CDN at runtime):
 *        npm pack @rdkit/rdkit        # do this on a build machine, not here
 *        # copy dist/RDKit_minimal.js and dist/RDKit_minimal.wasm into
 *        # web/mechgrader/vendor/rdkit/
 *   2) Load the loader script before this module (or inject it), e.g. in index.html:
 *        <script src="./vendor/rdkit/RDKit_minimal.js"></script>
 *      which defines window.initRDKitModule.
 *   3) At startup:
 *        import { loadRDKit } from "./rdkit.js";
 *        await loadRDKit({ locateFile: (f) => "./vendor/rdkit/" + f });
 *      After that, canonicalize()/productsMatch() automatically use real RDKit.
 */

let _rdkit = null; // the initialized RDKit module, once loaded

/**
 * Initialize RDKit-JS from a vendored offline mirror. Resolves to the RDKit
 * module. Throws (with a clear message) if the loader isn't present — callers
 * should catch and continue with the fallback rather than failing hard.
 */
export async function loadRDKit(opts = {}) {
  const init =
    opts.initRDKitModule ||
    (typeof window !== "undefined" ? window.initRDKitModule : undefined) ||
    (typeof globalThis !== "undefined" ? globalThis.initRDKitModule : undefined);
  if (typeof init !== "function") {
    throw new Error(
      "initRDKitModule not found — RDKit-JS is not vendored/loaded. " +
        "Staying on the string fallback. See the seam at the top of rdkit.js."
    );
  }
  _rdkit = await init({
    // Point the WASM loader at the offline mirror by default.
    locateFile: opts.locateFile || ((f) => "./vendor/rdkit/" + f),
  });
  return _rdkit;
}

/** True once real RDKit-JS is loaded. */
export function isRDKitReady() {
  return !!_rdkit;
}

/** For tests / advanced callers. */
export function setRDKitModule(mod) {
  _rdkit = mod || null;
}

/**
 * Canonicalize one SMILES string.
 * @returns {{smiles:string, canonical:boolean, valid:boolean}}
 *   canonical:true  -> real RDKit canonical SMILES
 *   canonical:false -> fallback (string only; NOT chemical canonicalization)
 */
export function canonicalize(smiles) {
  const s = String(smiles ?? "").trim();
  if (_rdkit) {
    let mol = null;
    try {
      mol = _rdkit.get_mol(s);
      if (mol && mol.is_valid()) {
        return { smiles: mol.get_smiles(), canonical: true, valid: true };
      }
      return { smiles: s, canonical: true, valid: false };
    } catch (_) {
      return { smiles: s, canonical: true, valid: false };
    } finally {
      if (mol && typeof mol.delete === "function") mol.delete();
    }
  }
  return fallbackCanonical(s);
}

/**
 * ⚠️ FALLBACK — NOT real canonicalization. It only trims whitespace and strips
 * atom-map numbers (so "[CH3:1]O" and "[CH3]O" don't differ *just* by mapping).
 * Connectivity, aromaticity, atom order, and stereochemistry are NOT normalized.
 */
export function fallbackCanonical(smiles) {
  const stripped = String(smiles ?? "")
    .trim()
    .replace(/:\d+\]/g, "]") // drop atom-map numbers: [CH3:1] -> [CH3]
    .replace(/\s+/g, "");
  return { smiles: stripped, canonical: false, valid: stripped.length > 0 };
}

/**
 * Compare two product sets as multisets of canonical SMILES.
 * @returns {{match:boolean, canonical:boolean, attempt:string[], reference:string[]}}
 *   canonical reflects whether RDKit was used (true) or the string fallback (false).
 */
export function productsMatch(attempt, reference) {
  const norm = (arr) =>
    (arr || [])
      .map((s) => canonicalize(s).smiles)
      .filter((s) => s && s.length)
      .sort();
  const a = norm(attempt);
  const b = norm(reference);
  const match = a.length === b.length && a.every((v, i) => v === b[i]);
  return { match, canonical: isRDKitReady(), attempt: a, reference: b };
}

/**
 * Offline fallback grade: an HONEST, minimal check — does the attempt's FINAL
 * product match the reference's final product? (+ light step-count / arrow-presence
 * signals). Real, layered grading (structures, transformations, mechanism type,
 * arrow-pushing, pathway) is the Python chem-grader's job; this is only what can
 * be checked client-side with no server.
 *
 * @param {object} mechanismObj serialized Mechanism { steps:[...] }
 * @param {object} referenceObj serialized reference Mechanism
 */
export function gradeAgainstReference(mechanismObj, referenceObj) {
  const steps = (mechanismObj && mechanismObj.steps) || [];
  const refSteps = (referenceObj && referenceObj.steps) || [];

  const finalProducts = steps.length ? steps[steps.length - 1].products : [];
  const refFinal = refSteps.length ? refSteps[refSteps.length - 1].products : [];

  const pm = productsMatch(finalProducts, refFinal);
  const stepCountMatch = steps.length === refSteps.length;
  const attemptHasArrows = steps.some((s) => (s.arrows || []).length > 0);
  const referenceHasArrows = refSteps.some((s) => (s.arrows || []).length > 0);

  let score = 0;
  if (pm.match) score += 70;
  if (stepCountMatch) score += 15;
  if (!referenceHasArrows || attemptHasArrows) score += 15;

  return {
    passed: pm.match,
    score,
    canonical: pm.canonical,
    engine: pm.canonical ? "rdkit-js (canonical SMILES)" : "fallback-string-match (NOT real canonicalization)",
    summary: pm.match
      ? "Final product matches the reference."
      : "Final product does not match the reference.",
    details: {
      finalProductMatch: pm,
      stepCount: { attempt: steps.length, reference: refSteps.length, match: stepCountMatch },
      arrows: { attemptHasArrows, referenceHasArrows },
    },
  };
}

export default {
  loadRDKit,
  isRDKitReady,
  setRDKitModule,
  canonicalize,
  fallbackCanonical,
  productsMatch,
  gradeAgainstReference,
};
