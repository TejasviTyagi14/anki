/*
 * chem.js — pure, DOM-free chemistry over a molecular graph.
 *
 * All functions operate on:
 *   atoms: [{ el, charge }]           (el like "C","O","N"; charge is an int)
 *   bonds: [{ a, b, order }]          (a,b are INDICES into atoms; order 1|2|3)
 *
 * The SVG editor keeps atoms/bonds keyed by id; the grader remaps id -> index
 * before calling in here. Keeping chem.js index-based is the single boundary.
 *
 * Loadable both as a browser global (window.Chem) and a Node module (for tests).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.Chem = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : null), function () {
  "use strict";

  // Neutral default valence used to derive implicit hydrogens. Elements not in
  // the table (e.g. metals) get no implicit H.
  const DEFAULT_VALENCE = { B: 3, C: 4, N: 3, O: 2, P: 3, S: 2, F: 1, Cl: 1, Br: 1, I: 1, H: 1 };

  // Atoms that may be written as a bare symbol in SMILES (no square brackets)
  // when neutral and within their default valence.
  const ORGANIC_SUBSET = new Set(["B", "C", "N", "O", "P", "S", "F", "Cl", "Br", "I"]);

  /** Sum of incident bond orders per atom (index-aligned with `atoms`). */
  function bondOrderSums(atoms, bonds) {
    const sums = atoms.map(() => 0);
    for (const b of bonds) {
      const o = b.order || 1;
      sums[b.a] += o;
      sums[b.b] += o;
    }
    return sums;
  }

  /**
   * SMILES-style implicit hydrogen count for one atom given its bond-order sum.
   * Charge shifts the effective valence:
   *   - positive charge: C and B LOSE valence (base - charge); everything
   *     else GAINS (base + charge)   -> N+ = 4, C+ = 3
   *   - negative charge: base + charge (charge is negative, so it subtracts)
   *     -> O- = 1, C- = 3
   */
  function implicitHydrogens(atom, orderSum) {
    const base = DEFAULT_VALENCE[atom.el];
    if (base === undefined) return 0;
    const charge = atom.charge || 0;
    let valence = base;
    if (charge > 0) {
      valence = atom.el === "C" || atom.el === "B" ? base - charge : base + charge;
    } else if (charge < 0) {
      valence = base + charge;
    }
    return Math.max(0, valence - orderSum);
  }

  /** Iterative DFS over an adjacency list -> arrays of atom indices, one per molecule. */
  function connectedComponents(atoms, bonds) {
    const adj = atoms.map(() => []);
    for (const b of bonds) {
      adj[b.a].push(b.b);
      adj[b.b].push(b.a);
    }
    const seen = new Array(atoms.length).fill(false);
    const comps = [];
    for (let i = 0; i < atoms.length; i++) {
      if (seen[i]) continue;
      const stack = [i];
      seen[i] = true;
      const comp = [];
      while (stack.length) {
        const u = stack.pop();
        comp.push(u);
        for (const v of adj[u]) {
          if (!seen[v]) {
            seen[v] = true;
            stack.push(v);
          }
        }
      }
      comp.sort((x, y) => x - y);
      comps.push(comp);
    }
    return comps;
  }

  /**
   * Kekulé SMILES for ONE connected molecule (no stereo descriptors — stereo is
   * reported separately from the drawing). atoms/bonds must be local (0-based).
   */
  function moleculeToSmiles(atoms, bonds) {
    const n = atoms.length;
    if (n === 0) return "";
    const orderSum = bondOrderSums(atoms, bonds);

    const adj = atoms.map(() => []);
    bonds.forEach((b, bi) => {
      adj[b.a].push({ to: b.b, bond: b, bi });
      adj[b.b].push({ to: b.a, bond: b, bi });
    });

    // Single DFS from atom 0 that classifies every bond exactly once: a bond to
    // an unvisited atom is a tree edge (childOrder[u]); a bond to an
    // already-visited atom is a ring closure. childOrder + ringBonds stay
    // consistent because they come from the same traversal.
    const seen = new Array(n).fill(false);
    const used = new Array(bonds.length).fill(false);
    const childOrder = atoms.map(() => []); // childOrder[u] = [{ to, bond }]
    const ringBonds = []; // [{ a, b, bond }]
    (function dfs(u) {
      seen[u] = true;
      for (const e of adj[u]) {
        if (used[e.bi]) continue;
        used[e.bi] = true;
        if (!seen[e.to]) {
          childOrder[u].push({ to: e.to, bond: e.bond });
          dfs(e.to);
        } else {
          ringBonds.push({ a: u, b: e.to, bond: e.bond });
        }
      }
    })(0);

    // Assign ring-closure digits, recorded at BOTH endpoints.
    const ringAt = new Map(); // atomIndex -> [{ digit, bond }]
    let digit = 0;
    for (const rb of ringBonds) {
      digit += 1;
      if (!ringAt.has(rb.a)) ringAt.set(rb.a, []);
      if (!ringAt.has(rb.b)) ringAt.set(rb.b, []);
      ringAt.get(rb.a).push({ digit, bond: rb.bond });
      ringAt.get(rb.b).push({ digit, bond: rb.bond });
    }
    const emitted = new Set();

    const digitStr = (d) => (d < 10 ? String(d) : "%" + String(d).padStart(2, "0"));
    const bondSym = (order) => (order === 2 ? "=" : order === 3 ? "#" : "");

    function atomToken(i) {
      const a = atoms[i];
      const charge = a.charge || 0;
      const base = DEFAULT_VALENCE[a.el];
      const bare = charge === 0 && ORGANIC_SUBSET.has(a.el) && base !== undefined && orderSum[i] <= base;
      if (bare) return a.el;
      let s = "[" + a.el;
      const h = implicitHydrogens(a, orderSum[i]);
      if (h === 1) s += "H";
      else if (h > 1) s += "H" + h;
      if (charge > 0) s += charge === 1 ? "+" : "+" + charge;
      else if (charge < 0) s += charge === -1 ? "-" : "-" + Math.abs(charge);
      return s + "]";
    }

    function write(u) {
      let s = atomToken(u);
      const rings = ringAt.get(u);
      if (rings) {
        for (const r of rings) {
          if (!emitted.has(r.digit)) {
            emitted.add(r.digit);
            s += bondSym(r.bond.order || 1) + digitStr(r.digit);
          } else {
            s += digitStr(r.digit);
          }
        }
      }
      const kids = childOrder[u];
      kids.forEach((c, idx) => {
        const sub = bondSym(c.bond.order || 1) + write(c.to);
        s += idx < kids.length - 1 ? "(" + sub + ")" : sub;
      });
      return s;
    }

    return write(0);
  }

  const SUP = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻" };
  const superscript = (str) => str.split("").map((c) => SUP[c] || c).join("");

  /** Hill-order molecular formula (C, then H, then alphabetical) with charge superscript. */
  function moleculeFormula(atoms, bonds) {
    const orderSum = bondOrderSums(atoms, bonds);
    const counts = {};
    let charge = 0;
    atoms.forEach((a, i) => {
      counts[a.el] = (counts[a.el] || 0) + 1;
      counts.H = (counts.H || 0) + implicitHydrogens(a, orderSum[i]);
      charge += a.charge || 0;
    });
    if (counts.H === 0) delete counts.H;

    const rank = (e) => (e === "C" ? 0 : e === "H" ? 1 : 2);
    const els = Object.keys(counts).sort((x, y) => rank(x) - rank(y) || (x < y ? -1 : x > y ? 1 : 0));

    let out = els.map((e) => e + (counts[e] > 1 ? counts[e] : "")).join("");
    if (charge !== 0) {
      const mag = Math.abs(charge);
      const sign = charge > 0 ? "+" : "-";
      out += mag === 1 ? superscript(sign) : superscript(String(mag) + sign);
    }
    return out;
  }

  return {
    DEFAULT_VALENCE,
    ORGANIC_SUBSET,
    bondOrderSums,
    implicitHydrogens,
    connectedComponents,
    moleculeToSmiles,
    moleculeFormula,
  };
});
