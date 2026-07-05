/**
 * draw.js — a lightweight, framework-free "click to draw a molecule" editor that
 * derives SMILES, for the MechGrader shared bundle. No React, no build step, so
 * the SAME bundle embeds in Anki's webview and an Android WebView.
 *
 * It adapts chem-grader's dependency-free graph->SMILES core (chem.js, vendored
 * here) and adds a small SVG canvas + an equivalent control set (element buttons,
 * add-atom, an A/B/order bond builder, undo, clear) so it is usable WITHOUT a
 * mouse (accessibility). Opened in a native <dialog> (focus trap + Esc for free).
 *
 * Molecule model (one representation): atoms [{id, el, charge, x, y}],
 * bonds [{a, b, order}] where a,b are atom ids. ids are remapped to indices only
 * at the chem.js boundary.
 */
import "./chem.js"; // UMD side effect: sets globalThis.Chem

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_W = 620;
const VIEW_H = 360;
const ELEMENTS = ["C", "O", "N", "H", "S", "P", "F", "Cl", "Br", "I"];
const EL_COLORS = {
  C: "#1f2328", H: "#5c6570", O: "#d32f2f", N: "#1565c0", S: "#b8860b",
  P: "#e65100", F: "#2e7d32", Cl: "#2e7d32", Br: "#8d3b1b", I: "#7b1fa2",
};

function el(tag, props = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k in n && k !== "list") n[k] = v;
    else n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}

// ── DOM-free graph -> SMILES/formula (unit-testable in node) ──────────────────
// atoms: [{id, el, charge}], bonds: [{a, b, order}] (a,b are atom ids).
export function graphToSmiles(atoms, bonds) {
  const Chem = globalThis.Chem;
  if (!Chem || !atoms.length) return "";
  const idx = new Map(atoms.map((a, i) => [a.id, i]));
  const catoms = atoms.map((a) => ({ el: a.el, charge: a.charge || 0 }));
  const cbonds = bonds.map((b) => ({ a: idx.get(b.a), b: idx.get(b.b), order: b.order }));
  return Chem.connectedComponents(catoms, cbonds)
    .map((comp) => {
      const loc = new Map(comp.map((g, l) => [g, l]));
      const la = comp.map((g) => catoms[g]);
      const lb = cbonds
        .filter((b) => loc.has(b.a) && loc.has(b.b))
        .map((b) => ({ a: loc.get(b.a), b: loc.get(b.b), order: b.order }));
      return Chem.moleculeToSmiles(la, lb);
    })
    .filter(Boolean)
    .join(".");
}

export function graphToFormula(atoms, bonds) {
  const Chem = globalThis.Chem;
  if (!Chem || !atoms.length) return "";
  const idx = new Map(atoms.map((a, i) => [a.id, i]));
  return Chem.moleculeFormula(
    atoms.map((a) => ({ el: a.el, charge: a.charge || 0 })),
    bonds.map((b) => ({ a: idx.get(b.a), b: idx.get(b.b), order: b.order }))
  );
}

export class StructureDrawer {
  constructor(container, opts = {}) {
    this.root = container;
    this.onChange = opts.onChange || null;
    this.atoms = [];
    this.bonds = [];
    this.nextId = 1;
    this.selected = null; // atom id staged for bonding
    this.currentEl = "C";
    this.currentCharge = 0;
    this.history = [];
    if (opts.smiles) this._seedNote = opts.smiles; // (display only; we don't parse SMILES in)
    this._build();
    this.render();
  }

  // ── derive SMILES/formula via the vendored chem.js core ──
  smiles() {
    return graphToSmiles(this.atoms, this.bonds);
  }
  formula() {
    return graphToFormula(this.atoms, this.bonds);
  }

  _snapshot() {
    this.history.push(JSON.stringify({ atoms: this.atoms, bonds: this.bonds, nextId: this.nextId }));
    if (this.history.length > 100) this.history.shift();
  }
  _restore() {
    const s = this.history.pop();
    if (!s) return;
    const st = JSON.parse(s);
    this.atoms = st.atoms;
    this.bonds = st.bonds;
    this.nextId = st.nextId;
    this.selected = null;
    this.render();
  }

  _addAtom(x, y) {
    this._snapshot();
    const a = { id: this.nextId++, el: this.currentEl, charge: this.currentCharge, x, y };
    this.atoms.push(a);
    this.render();
    return a.id;
  }

  _toggleBond(aId, bId) {
    if (aId === bId) return;
    this._snapshot();
    const b = this.bonds.find((x) => (x.a === aId && x.b === bId) || (x.a === bId && x.b === aId));
    if (!b) this.bonds.push({ a: aId, b: bId, order: 1 });
    else if (b.order < 3) b.order += 1;
    else this.bonds = this.bonds.filter((x) => x !== b); // 3 -> remove
    this.render();
  }

  _atom(id) {
    return this.atoms.find((a) => a.id === id);
  }

  _onCanvasClick(evt) {
    const pt = this._svgPoint(evt);
    const hit = this._atomAt(pt.x, pt.y);
    if (hit) {
      if (this.selected == null) this.selected = hit.id;
      else if (this.selected === hit.id) this.selected = null;
      else {
        this._toggleBond(this.selected, hit.id);
        this.selected = null;
      }
      this.render();
    } else {
      this._addAtom(pt.x, pt.y);
    }
  }

  _svgPoint(evt) {
    const r = this.svg.getBoundingClientRect();
    return {
      x: Math.round(((evt.clientX - r.left) / r.width) * VIEW_W),
      y: Math.round(((evt.clientY - r.top) / r.height) * VIEW_H),
    };
  }
  _atomAt(x, y) {
    return this.atoms.find((a) => (a.x - x) ** 2 + (a.y - y) ** 2 <= 20 * 20);
  }

  _build() {
    this.root.innerHTML = "";
    this.root.className = "draw-root";

    // element + charge toolbar
    this.elButtons = ELEMENTS.map((sym) =>
      el("button", {
        type: "button", class: "draw-el", "aria-pressed": sym === this.currentEl,
        text: sym, "aria-label": `Draw ${sym} atoms`,
        onClick: () => { this.currentEl = sym; this._syncEls(); },
      })
    );
    const charge = el("div", { class: "draw-charge", role: "group", "aria-label": "Formal charge for new atoms" }, [
      el("button", { type: "button", class: "btn draw-mini", text: "\u2212", "aria-label": "Decrease charge", onClick: () => { this.currentCharge -= 1; this._syncEls(); } }),
      (this.chargeLabel = el("span", { class: "draw-charge-val", "aria-live": "polite", text: "0" })),
      el("button", { type: "button", class: "btn draw-mini", text: "+", "aria-label": "Increase charge", onClick: () => { this.currentCharge += 1; this._syncEls(); } }),
    ]);
    const tools = el("div", { class: "draw-toolbar" }, [...this.elButtons, charge]);

    // svg canvas
    this.svg = document.createElementNS(SVG_NS, "svg");
    this.svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);
    this.svg.setAttribute("class", "draw-svg");
    this.svg.setAttribute("role", "img");
    this.svg.setAttribute("aria-label", "Molecule canvas: click empty space to add an atom, click an atom then another to bond");
    this.svg.addEventListener("click", (e) => this._onCanvasClick(e));

    // keyboard/equivalent control set (not mouse-only)
    this.bondA = el("select", { class: "select draw-sel", "aria-label": "Bond atom A" });
    this.bondB = el("select", { class: "select draw-sel", "aria-label": "Bond atom B" });
    const controls = el("div", { class: "draw-controls" }, [
      el("button", { type: "button", class: "btn", text: "+ Atom", "aria-label": "Add an atom (keyboard)", onClick: () => this._addAtomAuto() }),
      el("span", { class: "draw-ctrl-sep", text: "bond" }),
      this.bondA, el("span", { text: "\u2013" }), this.bondB,
      el("button", { type: "button", class: "btn", text: "Add / cycle bond", onClick: () => this._bondFromControls() }),
      el("span", { class: "grow" }),
      el("button", { type: "button", class: "btn btn-ghost", text: "Undo", onClick: () => this._restore() }),
      el("button", { type: "button", class: "btn btn-ghost", text: "Clear", onClick: () => { this._snapshot(); this.atoms = []; this.bonds = []; this.selected = null; this.render(); } }),
    ]);

    this.readout = el("div", { class: "draw-readout", "aria-live": "polite" });

    this.root.append(tools, this.svg, controls, this.readout);
    this._syncEls();
  }

  _syncEls() {
    this.currentCharge = Math.max(-4, Math.min(4, this.currentCharge));
    if (this.chargeLabel) this.chargeLabel.textContent = this.currentCharge > 0 ? `+${this.currentCharge}` : String(this.currentCharge);
    for (const b of this.elButtons) b.setAttribute("aria-pressed", String(b.textContent === this.currentEl));
  }

  _addAtomAuto() {
    // Place near the last atom (or center), offset so it doesn't overlap.
    const last = this.atoms[this.atoms.length - 1];
    const x = last ? Math.min(VIEW_W - 40, last.x + 60) : VIEW_W / 2;
    const y = last ? last.y : VIEW_H / 2;
    const id = this._addAtom(x, y);
    // auto-bond to the previous atom for quick chains
    if (last) this._toggleBond(last.id, id);
  }

  _bondFromControls() {
    const a = Number(this.bondA.value);
    const b = Number(this.bondB.value);
    if (a && b) this._toggleBond(a, b);
  }

  render() {
    // svg content
    const parts = [];
    for (const b of this.bonds) {
      const a1 = this._atom(b.a);
      const a2 = this._atom(b.b);
      if (!a1 || !a2) continue;
      const dx = a2.x - a1.x, dy = a2.y - a1.y;
      const len = Math.hypot(dx, dy) || 1;
      const ox = (-dy / len) * 4, oy = (dx / len) * 4; // perpendicular offset for multi-bonds
      const lines = b.order === 1 ? [0] : b.order === 2 ? [-1, 1] : [-1, 0, 1];
      for (const m of lines) {
        parts.push(`<line x1="${a1.x + ox * m}" y1="${a1.y + oy * m}" x2="${a2.x + ox * m}" y2="${a2.y + oy * m}" class="draw-bond"/>`);
      }
    }
    for (const a of this.atoms) {
      const sel = a.id === this.selected;
      const color = EL_COLORS[a.el] || "#7b1fa2";
      if (sel) parts.push(`<circle cx="${a.x}" cy="${a.y}" r="19" class="draw-atom-sel"/>`);
      parts.push(`<circle cx="${a.x}" cy="${a.y}" r="15" class="draw-atom-bg"/>`);
      parts.push(`<text x="${a.x}" y="${a.y}" text-anchor="middle" dominant-baseline="central" class="draw-atom-el" fill="${color}">${escapeXml(a.el)}</text>`);
      if (a.charge) {
        const c = a.charge > 0 ? (a.charge === 1 ? "+" : `+${a.charge}`) : (a.charge === -1 ? "\u2212" : `\u2212${Math.abs(a.charge)}`);
        parts.push(`<text x="${a.x + 15}" y="${a.y - 12}" text-anchor="middle" class="draw-atom-charge">${c}</text>`);
      }
      parts.push(`<text x="${a.x}" y="${a.y + 22}" text-anchor="middle" class="draw-atom-id">${a.id}</text>`);
    }
    if (!this.atoms.length) {
      parts.push(`<text x="${VIEW_W / 2}" y="${VIEW_H / 2}" text-anchor="middle" dominant-baseline="middle" class="draw-empty">Click to add a ${this.currentEl} atom · click two atoms to bond</text>`);
    }
    this.svg.innerHTML = parts.join("");

    // bond-control selects
    const opts = this.atoms.map((a) => `<option value="${a.id}">${a.id}: ${a.el}</option>`).join("");
    this.bondA.innerHTML = opts;
    this.bondB.innerHTML = opts;
    if (this.atoms[1]) this.bondB.value = String(this.atoms[this.atoms.length - 1].id);

    // readout
    const smi = this.smiles();
    this.readout.textContent = smi ? `SMILES: ${smi}   ·   ${this.formula()}` : "Draw a molecule to see its SMILES.";
    if (typeof this.onChange === "function") this.onChange(smi);
  }
}

function escapeXml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * Open the drawer in a native <dialog> (focus trap + Esc close for free) and
 * resolve with the drawn SMILES on "Use", or null on cancel.
 */
export function openStructureDialog(opts = {}) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { class: "draw-dialog", "aria-label": "Draw a molecule" });
    const mount = el("div");
    const drawer = new StructureDrawer(mount, {});
    const use = el("button", {
      type: "button", class: "btn btn-primary", text: "Use this structure",
      onClick: () => { const s = drawer.smiles(); close(s || null); },
    });
    const cancel = el("button", { type: "button", class: "btn btn-ghost", text: "Cancel", onClick: () => close(null) });
    const bar = el("div", { class: "draw-dialog-bar" }, [
      el("span", { class: "draw-dialog-title", text: opts.title || "Draw a molecule" }),
      el("span", { class: "grow" }), cancel, use,
    ]);
    dialog.append(bar, mount);
    document.body.appendChild(dialog);

    function close(result) {
      try { dialog.close(); } catch (_) {}
      dialog.remove();
      resolve(result);
    }
    dialog.addEventListener("cancel", () => close(null)); // Esc
    dialog.showModal();
  });
}

export default StructureDrawer;
