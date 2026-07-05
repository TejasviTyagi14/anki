/**
 * editor.js — the MechGrader step editor (framework-free ES module).
 *
 * Builds the interactive UI inside a root element:
 *   • a read-only "prompt" pin (the card front),
 *   • an active-step structure workspace containing the Ketcher mount seam
 *     (#ketcher-slot) with a working SMILES-text fallback so the editor is fully
 *     usable WITHOUT Ketcher,
 *   • the curved-arrow tool (arrows.js ArrowOverlay) + a keyboard-accessible
 *     "From / To / Add arrow" control set (not mouse-only),
 *   • step add/remove and per-step reactant/product SMILES inputs,
 *   • a Submit button that assembles the Mechanism JSON and dispatches a grade:
 *       window.mechgraderGrade(mechanism)  if defined, else
 *       POST JSON to a configurable gradeEndpoint, else
 *       just returns the assembled mechanism (the page shows it).
 *
 * The editor owns the data (a Mechanism from mechanism.js); the overlay is a
 * view+input that reflects the active step's arrows.
 */
import { Mechanism } from "./mechanism.js";
import { ArrowOverlay, layoutAnchorsLinear } from "./arrows.js";

const VIEW_W = 900;
const VIEW_H = 300;
const SVG_NS = "http://www.w3.org/2000/svg";

// Element colors for the fallback depiction (mirrors chem-grader's palette).
const EL_COLORS = {
  C: "#1f2328",
  H: "#5c6570",
  O: "#d32f2f",
  N: "#1565c0",
  S: "#b8860b",
  P: "#e65100",
  F: "#2e7d32",
  Cl: "#2e7d32",
  Br: "#8d3b1b",
  I: "#7b1fa2",
};

// One-click reactants/reagents so a student can build a reaction without
// hand-writing SMILES (the biggest intuitiveness win short of a full visual
// editor). Plain SMILES; the grader canonicalizes, and atom-map numbers are only
// needed on arrow endpoints, not for entering structures.
const COMMON_FRAGMENTS = [
  { label: "water", smiles: "O" },
  { label: "hydroxide", smiles: "[OH-]" },
  { label: "bromide", smiles: "[Br-]" },
  { label: "CH\u2083Br", smiles: "CBr" },
  { label: "t-BuBr", smiles: "CC(C)(C)Br" },
  { label: "cyanide", smiles: "[C-]#N" },
  { label: "formaldehyde", smiles: "C=O" },
  { label: "ammonia", smiles: "N" },
  { label: "ethanol", smiles: "CCO" },
  { label: "ethene", smiles: "C=C" },
  { label: "benzene", smiles: "c1ccccc1" },
];

// ── tiny DOM helper ──────────────────────────────────────────────────────────
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k in node && k !== "list") node[k] = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

/**
 * Extract heavy atoms (non-H) from a SMILES string in order, returning their
 * element symbols. Used ONLY to build the offline fallback depiction + anchors.
 *
 * ⚠️ This is a light tokenizer, not a SMILES parser: it lists heavy atoms in
 * written order and does not expand implicit atoms, resolve ring closures, or
 * infer real bond topology. Real atom indexing + coordinates come from Ketcher
 * (molfile) or RDKit-JS. The 0-based order here matches the arrow endpoints'
 * "atom index into the reactant" convention.
 */
export function tokenizeHeavyAtoms(smiles) {
  const s = String(smiles || "");
  const out = [];
  const twoLetter = new Set(["Cl", "Br"]);
  const organic = new Set(["B", "C", "N", "O", "P", "S", "F", "I"]);
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (ch === "[") {
      const end = s.indexOf("]", i);
      if (end === -1) break;
      const sym = bracketSymbol(s.slice(i + 1, end));
      if (sym && sym.toUpperCase() !== "H") out.push(sym);
      i = end + 1;
      continue;
    }
    const two = s.slice(i, i + 2);
    if (twoLetter.has(two)) {
      out.push(two);
      i += 2;
      continue;
    }
    if (organic.has(ch)) {
      out.push(ch);
      i += 1;
      continue;
    }
    if ("bcnops".includes(ch)) {
      out.push(ch.toUpperCase());
      i += 1;
      continue;
    }
    i += 1; // skip bonds, digits, parens, %, charges outside brackets, etc.
  }
  return out;
}

function bracketSymbol(inner) {
  // "CH3:1" -> C, "O-" -> O, "NH2+" -> N, "13CH3" -> C, "se" -> Se
  const m = inner.match(/^\d*(Cl|Br|[A-Z][a-z]?|se|as|[bcnops])/);
  if (!m) return null;
  const sym = m[1];
  return sym.length === 2 && sym === sym.toLowerCase() ? sym[0].toUpperCase() + sym[1] : sym;
}

export class MechEditor {
  /**
   * @param {Element} root
   * @param {object} opts
   *   prompt          string, the read-only prompt pin
   *   mechanism       Mechanism | serialized object (initial state)
   *   gradeEndpoint   string, POST fallback when window.mechgraderGrade is absent
   *   onSubmit(mechanism, grade, error)  called after Submit
   *   onFlip()        study-loop "flip" hook (see standalone page shortcuts)
   *   onNext()        study-loop "next" hook
   */
  constructor(root, opts = {}) {
    this.root = root;
    this.onSubmit = opts.onSubmit || null;
    this.onFlip = opts.onFlip || null;
    this.onNext = opts.onNext || null;
    this.gradeEndpoint = opts.gradeEndpoint || "";
    this.prompt = opts.prompt || "";

    this.mechanism =
      opts.mechanism instanceof Mechanism ? opts.mechanism : Mechanism.deserialize(opts.mechanism || { steps: [{}] });
    if (this.mechanism.length === 0) this.mechanism.addStep({});
    this.activeStep = 0;

    this._build();
    this.renderAll();
  }

  // ── public API ──────────────────────────────────────────────────────────────
  getMechanism() {
    return this.mechanism;
  }

  /** Plain serialized object (exactly the grader's JSON shape). */
  getSerialized() {
    return this.mechanism.serialize();
  }

  setPrompt(text) {
    this.prompt = text || "";
    this.els.promptText.textContent = this.prompt || "(no prompt)";
  }

  /** Reset to a fresh card: new prompt + a new (single empty) mechanism. */
  reset(prompt, mechanism) {
    this.prompt = prompt || "";
    this.mechanism =
      mechanism instanceof Mechanism ? mechanism : Mechanism.deserialize(mechanism || { steps: [{}] });
    if (this.mechanism.length === 0) this.mechanism.addStep({});
    this.activeStep = 0;
    this.renderAll();
  }

  flip() {
    if (typeof this.onFlip === "function") this.onFlip();
  }

  next() {
    if (typeof this.onNext === "function") this.onNext();
  }

  /** Assemble the Mechanism JSON and dispatch grading. Returns {mechanism, grade, error}. */
  async submit() {
    const mechanism = this.getSerialized();
    let grade = null;
    let error = null;
    try {
      if (typeof window !== "undefined" && typeof window.mechgraderGrade === "function") {
        grade = await window.mechgraderGrade(mechanism);
      } else if (this.gradeEndpoint) {
        const res = await fetch(this.gradeEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(mechanism),
        });
        if (!res.ok) throw new Error(`gradeEndpoint returned ${res.status}`);
        grade = await res.json();
      }
    } catch (e) {
      error = e;
    }
    if (typeof this.onSubmit === "function") this.onSubmit(mechanism, grade, error);
    return { mechanism, grade, error };
  }

  // ── build the DOM skeleton once ──────────────────────────────────────────────
  _build() {
    this.root.classList.add("mech-editor");
    this.root.innerHTML = "";
    this.els = {};

    // Read-only prompt pin.
    this.els.promptText = el("p", { class: "mech-prompt-text" });
    const prompt = el("div", { class: "mech-prompt card", role: "note", "aria-label": "Prompt" }, [
      el("span", { class: "mech-pin", text: "Prompt" }),
      this.els.promptText,
    ]);

    // Active-step structure workspace.
    this.els.structureStatus = el("span", {
      class: "mech-structure-status",
      "aria-live": "polite",
    });
    const head = el("div", { class: "mech-structure-head" }, [
      el("span", { class: "mech-structure-title", text: "\u2461 Push electron-pushing arrows" }),
      this.els.structureStatus,
    ]);
    const workspaceHelp = el("p", {
      class: "mech-help",
      html:
        "Click a <b>source</b> (a bond, lone pair, or atom) then its <b>target</b> to draw a curved " +
        "arrow — or pick <b>From/To</b> below. The picture shows the active step's reactants; " +
        "each atom shows its <b>index</b> (used by arrow endpoints).",
    });

    // #ketcher-slot: the documented Ketcher mount point (structure layer).
    //
    // ── KETCHER INTEGRATION SEAM ────────────────────────────────────────────
    // Without Ketcher we render a lightweight SMILES-derived depiction into this
    // slot so the arrow tool is fully usable. To mount real Ketcher instead:
    //
    //   1) Vendor ketcher-standalone offline (no CDN) — see README.
    //   2) Mount it into #ketcher-slot, e.g.:
    //        import { Editor } from "ketcher-standalone"; // vendored
    //        const ketcher = await StandaloneStructServiceProvider... // per Ketcher docs
    //        // or the <ketcher-editor> web component appended into slot.
    //   3) Hide the fallback depiction (this.structureSvg.style.display = "none").
    //   4) When the user finishes drawing, read the structure and update the step:
    //        const molfile = await ketcher.getMolfile();   // MDL molfile (2D coords)
    //        const smiles  = await ketcher.getSmiles();    // canonical-ish SMILES
    //        step.reactants[0] = smiles;                   // keep the data model in sync
    //        editor.setAnchorsFromMolfile(molfile);        // real atom coords -> anchors
    //   setAnchorsFromMolfile() (below) maps molfile atom lines to overlay anchors,
    //   so the SAME curved-arrow overlay works unchanged over Ketcher's drawing.
    this.els.slot = el("div", { id: "ketcher-slot", class: "ketcher-slot", "aria-label": "Structure editor" });
    this.structureSvg = document.createElementNS(SVG_NS, "svg");
    this.structureSvg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);
    this.structureSvg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.structureSvg.setAttribute("class", "mech-structure-svg");
    this.structureSvg.setAttribute("role", "img");
    this.structureSvg.setAttribute("aria-label", "Simplified reactant depiction (SMILES fallback)");
    this.els.slot.appendChild(this.structureSvg);

    this.els.structure = el("div", { class: "mech-structure", id: "mech-structure" }, [this.els.slot]);

    // Curved-arrow overlay on top of the structure region.
    this.overlay = new ArrowOverlay(this.els.structure, {
      viewW: VIEW_W,
      viewH: VIEW_H,
      onArrowsChange: (list) => this._onOverlayArrowsChange(list),
      onStatus: (msg) => {
        this.els.structureStatus.textContent = msg;
      },
    });

    // Keyboard-accessible arrow controls (equivalent to clicking — not mouse-only).
    this.els.arrowFrom = el("select", { class: "select mech-arrow-from", "aria-label": "Arrow source endpoint" });
    this.els.arrowTo = el("select", { class: "select mech-arrow-to", "aria-label": "Arrow target endpoint" });
    const addArrowBtn = el("button", {
      class: "btn mech-add-arrow",
      type: "button",
      text: "Add curved arrow",
      onClick: () => this._addArrowFromControls(),
    });
    const arrowControls = el("div", { class: "mech-arrow-controls", role: "group", "aria-label": "Add arrow by endpoint" }, [
      el("label", { class: "mech-field" }, [el("span", { text: "From" }), this.els.arrowFrom]),
      el("label", { class: "mech-field" }, [el("span", { text: "To" }), this.els.arrowTo]),
      addArrowBtn,
    ]);

    this.els.arrowList = el("ul", { class: "mech-arrow-list", "aria-label": "Curved arrows in the active step" });

    const workspace = el("div", { class: "mech-workspace card" }, [
      head,
      workspaceHelp,
      this.els.structure,
      arrowControls,
      this.els.arrowList,
    ]);

    // Steps list + add.
    this.els.steps = el("div", { class: "mech-steps" });
    const addStep = el("button", {
      class: "btn mech-add-step",
      type: "button",
      text: "+ Add step",
      onClick: () => {
        this.mechanism.addStep({});
        this.activeStep = this.mechanism.length - 1;
        this.renderAll();
      },
    });

    // Submit (the single primary action).
    this.els.submit = el("button", {
      class: "btn btn-primary mech-submit",
      type: "button",
      text: "Submit",
      onClick: () => this.submit(),
    });

    // Guided order: enter the molecules first (Structures), then push arrows on
    // the active step (Workspace), then Submit.
    this.root.append(
      prompt,
      el("div", { class: "mech-steps-wrap" }, [
        el("div", { class: "mech-steps-head" }, [
          el("h2", { class: "mech-h2", text: "\u2460 Structures" }),
          addStep,
        ]),
        el("p", {
          class: "mech-help",
          html:
            "Type each molecule's SMILES, or tap a <b>quick-insert</b> chip. Pick one step " +
            "<b>active</b> to push its arrows above; add products before submitting.",
        }),
        this.els.steps,
      ]),
      workspace,
      el("div", { class: "mech-actions" }, [this.els.submit])
    );
  }

  // ── full render ──────────────────────────────────────────────────────────────
  renderAll() {
    this.setPrompt(this.prompt);
    this._clampActive();
    this._renderSteps();
    this._renderWorkspace();
  }

  _clampActive() {
    if (this.activeStep >= this.mechanism.length) this.activeStep = this.mechanism.length - 1;
    if (this.activeStep < 0) this.activeStep = 0;
  }

  _activeStepObj() {
    return this.mechanism.step(this.activeStep) || this.mechanism.step(0);
  }

  _renderSteps() {
    this.els.steps.innerHTML = "";
    this.mechanism.steps.forEach((step, idx) => {
      const isActive = idx === this.activeStep;

      const radio = el("input", {
        type: "radio",
        name: "mech-active-step",
        checked: isActive,
        "aria-label": `Make step ${idx + 1} active`,
        onChange: () => {
          this.activeStep = idx;
          this._renderSteps();
          this._renderWorkspace();
        },
      });
      const removeBtn = el("button", {
        class: "btn btn-ghost mech-step-remove",
        type: "button",
        text: "Remove",
        "aria-label": `Remove step ${idx + 1}`,
        disabled: this.mechanism.length <= 1,
        onClick: () => {
          this.mechanism.removeStep(idx);
          if (this.mechanism.length === 0) this.mechanism.addStep({});
          if (this.activeStep >= this.mechanism.length) this.activeStep = this.mechanism.length - 1;
          this.renderAll();
        },
      });
      const stepHead = el("div", { class: "mech-step-head" }, [
        el("label", { class: "mech-step-active" }, [radio, el("span", { text: `Step ${idx + 1}` })]),
        removeBtn,
      ]);

      const reactants = this._molGroup(step, "reactants", idx);
      const products = this._molGroup(step, "products", idx);
      const summary = el("div", {
        class: "mech-step-arrows-summary",
        text: `Arrows: ${step.arrows.length}`,
      });

      const card = el(
        "div",
        { class: `mech-step card${isActive ? " is-active" : ""}`, dataset: { index: String(idx) } },
        [stepHead, reactants, products, summary]
      );
      this.els.steps.appendChild(card);
    });
  }

  _molGroup(step, role, stepIdx) {
    const list = el("ul", { class: "mech-mol-list" });
    const items = step[role];
    const singular = role === "reactants" ? "Reactant" : "Product";

    items.forEach((smiles, i) => {
      const input = el("input", {
        class: "input mech-smiles",
        type: "text",
        value: smiles,
        placeholder: role === "reactants" ? "e.g. [CH3:1][Br:2]" : "e.g. [CH3:1][OH:3]",
        "aria-label": `${singular} ${i + 1} SMILES (step ${stepIdx + 1})`,
        onInput: (e) => {
          if (role === "reactants") step.setReactant(i, e.target.value);
          else step.setProduct(i, e.target.value);
          if (stepIdx === this.activeStep && role === "reactants") this._renderWorkspace();
        },
      });
      const remove = el("button", {
        class: "btn btn-ghost mech-mol-remove",
        type: "button",
        text: "\u00d7",
        "aria-label": `Remove ${singular.toLowerCase()} ${i + 1}`,
        onClick: () => {
          if (role === "reactants") step.removeReactant(i);
          else step.removeProduct(i);
          this._renderSteps();
          if (stepIdx === this.activeStep) this._renderWorkspace();
        },
      });
      list.appendChild(el("li", { class: "mech-mol-row" }, [input, remove]));
    });

    const add = el("button", {
      class: "btn mech-add-mol",
      type: "button",
      text: `+ ${singular} SMILES`,
      onClick: () => {
        if (role === "reactants") step.addReactant("");
        else step.addProduct("");
        this._renderSteps();
        if (stepIdx === this.activeStep && role === "reactants") this._renderWorkspace();
      },
    });

    const children = [
      el("div", { class: "mech-molgroup-head" }, [el("span", { text: singular + "s" }), add]),
      list,
    ];
    // Quick-insert palette for reactants: one tap adds a common molecule so
    // students don't have to hand-write SMILES.
    if (role === "reactants") {
      const palette = el(
        "div",
        { class: "mech-frag-palette", role: "group", "aria-label": "Insert a common reactant" },
        COMMON_FRAGMENTS.map((f) =>
          el("button", {
            class: "mech-frag",
            type: "button",
            text: f.label,
            title: `Add ${f.label} (${f.smiles})`,
            onClick: () => {
              step.addReactant(f.smiles);
              this._renderSteps();
              if (stepIdx === this.activeStep) this._renderWorkspace();
            },
          })
        )
      );
      children.push(palette);
    }
    return el("div", { class: "mech-molgroup", dataset: { role } }, children);
  }

  // ── active-step structure + arrows ───────────────────────────────────────────
  _renderWorkspace() {
    const step = this._activeStepObj();
    const molecules = step.reactants.map((s) => tokenizeHeavyAtoms(s));
    const layout = layoutAnchorsLinear(molecules, { width: VIEW_W, height: VIEW_H });
    this._lastLayout = layout;

    this._drawStructure(layout);
    this.overlay.setAnchors(layout.anchors);
    this.overlay.setArrows(step.serialize().arrows);
    this._populateArrowControls(layout.anchors);
    this._renderArrowList(step, layout.anchors);
    this.overlay._status();
  }

  _drawStructure(layout) {
    const parts = [];
    if (!layout.atoms.length) {
      parts.push(
        `<text x="${VIEW_W / 2}" y="${VIEW_H / 2}" text-anchor="middle" dominant-baseline="middle" ` +
          `class="mech-structure-empty">Add a reactant SMILES to enable the arrow tool</text>`
      );
      this.structureSvg.innerHTML = parts.join("");
      return;
    }
    for (const b of layout.bonds) {
      parts.push(
        `<line x1="${b.x1}" y1="${b.y1}" x2="${b.x2}" y2="${b.y2}" class="mech-bond"/>`
      );
    }
    for (const a of layout.atoms) {
      const color = EL_COLORS[a.symbol] || "#7b1fa2";
      parts.push(`<circle cx="${a.x}" cy="${a.y}" r="13" class="mech-atom-bg"/>`);
      parts.push(
        `<text x="${a.x}" y="${a.y}" text-anchor="middle" dominant-baseline="central" ` +
          `class="mech-atom-label" fill="${color}">${escapeXml(a.symbol)}</text>`
      );
      parts.push(
        `<text x="${a.x}" y="${a.y + 20}" text-anchor="middle" dominant-baseline="central" ` +
          `class="mech-atom-index">${a.index}</text>`
      );
    }
    this.structureSvg.innerHTML = parts.join("");
  }

  _populateArrowControls(anchors) {
    const build = (select) => {
      const prev = select.value;
      select.innerHTML = "";
      const groups = { atom: [], bond: [], lp: [] };
      for (const a of anchors) groups[a.type] ? groups[a.type].push(a) : null;
      const labels = { atom: "Atoms", bond: "Bonds", lp: "Lone pairs" };
      for (const type of ["atom", "bond", "lp"]) {
        if (!groups[type].length) continue;
        const og = el("optgroup", { label: labels[type] });
        for (const a of groups[type]) {
          og.appendChild(el("option", { value: a.endpoint, text: `${a.endpoint}  (${a.label || ""})` }));
        }
        select.appendChild(og);
      }
      if (prev && anchors.some((a) => a.endpoint === prev)) select.value = prev;
    };
    build(this.els.arrowFrom);
    build(this.els.arrowTo);
    const disabled = anchors.length === 0;
    this.els.arrowFrom.disabled = disabled;
    this.els.arrowTo.disabled = disabled;
  }

  _addArrowFromControls() {
    const from = this.els.arrowFrom.value;
    const to = this.els.arrowTo.value;
    if (!from || !to) return;
    this.overlay.addArrow(from, to); // fires onArrowsChange -> writes into the step
  }

  _onOverlayArrowsChange(list) {
    const step = this._activeStepObj();
    step.setArrows(list);
    this._renderArrowList(step, this._lastLayout ? this._lastLayout.anchors : []);
    // Refresh the "Arrows: N" summary on the active step card.
    const card = this.els.steps.querySelector(`.mech-step[data-index="${this.activeStep}"] .mech-step-arrows-summary`);
    if (card) card.textContent = `Arrows: ${step.arrows.length}`;
  }

  _renderArrowList(step, anchors) {
    const labelFor = (endpoint) => {
      const a = (anchors || []).find((x) => x.endpoint === endpoint);
      return a && a.label ? `${endpoint} (${a.label})` : endpoint;
    };
    this.els.arrowList.innerHTML = "";
    if (!step.arrows.length) {
      this.els.arrowList.appendChild(el("li", { class: "mech-arrow-empty", text: "No arrows yet." }));
      return;
    }
    step.arrows.forEach((arrow, i) => {
      const remove = el("button", {
        class: "btn btn-ghost mech-arrow-remove",
        type: "button",
        text: "Remove",
        "aria-label": `Remove arrow ${i + 1}`,
        onClick: () => this.overlay.removeArrow(i), // fires onArrowsChange
      });
      const text = el("span", {
        class: "mech-arrow-text",
        text: `${labelFor(arrow.from)}  \u2192  ${labelFor(arrow.to)}`,
      });
      this.els.arrowList.appendChild(el("li", { class: "mech-arrow-item" }, [text, remove]));
    });
  }

  /**
   * KETCHER SEAM helper: turn an MDL molfile (V2000) into overlay anchors using
   * the real 2D atom coordinates, so the same curved-arrow overlay works over a
   * Ketcher drawing. Called by an integrator after ketcher.getMolfile().
   * (Kept simple + defensive; returns the anchors it set.)
   */
  setAnchorsFromMolfile(molfile) {
    const anchors = anchorsFromMolfile(molfile, { width: VIEW_W, height: VIEW_H });
    this.overlay.setAnchors(anchors);
    this._lastLayout = { anchors, atoms: [], bonds: [] };
    this._populateArrowControls(anchors);
    return anchors;
  }
}

// ── molfile (V2000) -> anchors, for the Ketcher seam ─────────────────────────
export function anchorsFromMolfile(molfile, opts = {}) {
  const width = opts.width ?? VIEW_W;
  const height = opts.height ?? VIEW_H;
  const lines = String(molfile || "").split(/\r?\n/);
  if (lines.length < 4) return [];
  const counts = lines[3];
  const nAtoms = parseInt(counts.slice(0, 3), 10);
  const nBonds = parseInt(counts.slice(3, 6), 10);
  if (!Number.isFinite(nAtoms) || nAtoms <= 0) return [];

  const atoms = [];
  for (let k = 0; k < nAtoms; k++) {
    const line = lines[4 + k] || "";
    const x = parseFloat(line.slice(0, 10));
    const y = parseFloat(line.slice(10, 20));
    const symbol = (line.slice(31, 34) || "").trim() || "C";
    atoms.push({ x, y, symbol });
  }
  // Normalize molfile coordinates (y is up in molfiles) into the viewBox.
  const xs = atoms.map((a) => a.x);
  const ys = atoms.map((a) => a.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padX = 70;
  const padY = 50;
  const sx = maxX > minX ? (width - 2 * padX) / (maxX - minX) : 1;
  const sy = maxY > minY ? (height - 2 * padY) / (maxY - minY) : 1;
  const scale = Math.min(sx, sy);
  const project = (a) => ({
    x: Math.round(padX + (a.x - minX) * scale),
    y: Math.round(height - padY - (a.y - minY) * scale), // flip y
  });

  const anchors = [];
  atoms.forEach((a, idx) => {
    const p = project(a);
    anchors.push({ endpoint: `atom:${idx}`, x: p.x, y: p.y, type: "atom", label: a.symbol });
    if (!/^[Cc]$/.test(a.symbol) && a.symbol.toUpperCase() !== "H") {
      anchors.push({ endpoint: `lp:${idx}`, x: p.x, y: p.y - 26, type: "lp", label: `lp ${a.symbol}` });
    }
  });
  for (let k = 0; k < nBonds; k++) {
    const line = lines[4 + nAtoms + k] || "";
    const i = parseInt(line.slice(0, 3), 10) - 1; // molfile atoms are 1-based
    const j = parseInt(line.slice(3, 6), 10) - 1;
    if (i >= 0 && j >= 0 && atoms[i] && atoms[j]) {
      const pi = project(atoms[i]);
      const pj = project(atoms[j]);
      anchors.push({
        endpoint: `bond:${i}-${j}`,
        x: Math.round((pi.x + pj.x) / 2),
        y: Math.round((pi.y + pj.y) / 2),
        type: "bond",
        label: `${atoms[i].symbol}\u2013${atoms[j].symbol}`,
      });
    }
  }
  return anchors;
}

function escapeXml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export default MechEditor;
