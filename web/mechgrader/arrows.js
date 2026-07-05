/**
 * arrows.js — the curved-arrow (electron-pushing) overlay for MechGrader.
 *
 * Framework-free ES module. It does NOT know how the structure underneath is
 * drawn — Ketcher, an <svg>, an <img>, or the SMILES text fallback all work,
 * because the overlay talks to the structure ONLY through "anchors" (points in a
 * shared SVG coordinate space).
 *
 * ── DATA FIRST, RENDER SECOND ────────────────────────────────────────────────
 * The source of truth is `this.arrows`: an array of { from, to, kind:"curved" }
 * using mechanism.js endpoint tokens ("atom:i" | "bond:i-j" | "lp:i"). Recording
 * an arrow ONLY mutates that array (and fires onArrowsChange). Rendering is a
 * pure function of (arrows, anchors): render() resolves each endpoint to an
 * {x,y} through the anchor map, then draws a quadratic Bézier. If an endpoint
 * can't be resolved yet (e.g. the structure has no coordinates), the arrow stays
 * in the data and is simply skipped by the renderer — nothing is ever lost.
 *
 * ── ANCHORS ──────────────────────────────────────────────────────────────────
 * An anchor is { endpoint, x, y, type?, label? } in the overlay's viewBox space
 * (default 0..900 × 0..300). Supply them with setAnchors(); the overlay
 * hit-tests clicks against them so the user can pick a source then a target.
 *   • SMILES fallback: editor.js lays atoms on a baseline (layoutAnchorsLinear).
 *   • Ketcher: build anchors from molfile 2D coordinates (see editor.js + README).
 * The overlay itself is chemistry-agnostic.
 */
import { normalizeArrow } from "./mechanism.js";

const SVG_NS = "http://www.w3.org/2000/svg";

const DEFAULTS = {
  viewW: 900,
  viewH: 300,
  curvature: 0.28, // control-point offset as a fraction of the chord length
  minBow: 26, // minimum perpendicular bow (viewBox units) so short arrows still curve
  hitRadius: 22, // click tolerance for anchors (viewBox units)
  arrowHitRadius: 12, // click tolerance for selecting an existing arrow
};

/**
 * Lay out a set of molecules (each an array of heavy-atom symbols) along a
 * horizontal baseline and return drawable geometry + overlay anchors. Pure
 * geometry: no chemistry knowledge beyond "heteroatoms get a lone pair anchor".
 * This is one *source* of anchors (the offline fallback); Ketcher/RDKit provide
 * another. Atom indices are global and 0-based across the concatenated reactants,
 * which is exactly what the arrow endpoints reference.
 *
 * @returns {{atoms:Array,bonds:Array,anchors:Array,width:number,height:number}}
 */
export function layoutAnchorsLinear(molecules, opts = {}) {
  const width = opts.width ?? DEFAULTS.viewW;
  const height = opts.height ?? DEFAULTS.viewH;
  const padX = opts.padX ?? 70;
  const baseline = opts.y ?? height / 2;
  const bondRise = opts.bondRise ?? 16; // zig-zag amplitude for a skeletal feel

  const mols = (molecules || []).map((m) => (Array.isArray(m) ? m : [])).filter((m) => m.length);
  const total = mols.reduce((n, m) => n + m.length, 0);

  const atoms = []; // {index, symbol, x, y, molecule}
  const bonds = []; // {i, j, x1, y1, x2, y2}
  const anchors = []; // {endpoint, x, y, type, label}

  if (total === 0) return { atoms, bonds, anchors, width, height };

  // Sequence of horizontal slots: every atom takes a slot, plus one extra slot
  // as a visual gap between separate molecules.
  const slots = total + Math.max(0, mols.length - 1);
  const dx = slots > 1 ? (width - 2 * padX) / (slots - 1) : 0;

  let slot = 0;
  let gIndex = 0;
  const isHetero = (s) => !/^[Cc]$/.test(s) && s.toUpperCase() !== "H";

  mols.forEach((mol, mi) => {
    let prevIndex = -1;
    mol.forEach((symbol, li) => {
      const x = Math.round(padX + slot * dx);
      const y = Math.round(baseline + (li % 2 === 0 ? -bondRise : bondRise));
      atoms.push({ index: gIndex, symbol, x, y, molecule: mi });
      anchors.push({ endpoint: `atom:${gIndex}`, x, y, type: "atom", label: symbol });

      // Lone-pair affordance for heteroatoms, placed just above the atom.
      if (isHetero(symbol)) {
        anchors.push({ endpoint: `lp:${gIndex}`, x, y: y - 26, type: "lp", label: `lp ${symbol}` });
      }

      // Bond anchor between consecutive atoms of the SAME molecule.
      if (prevIndex >= 0) {
        const a = atoms[prevIndex];
        const b = atoms[atoms.length - 1];
        bonds.push({ i: a.index, j: b.index, x1: a.x, y1: a.y, x2: b.x, y2: b.y });
        anchors.push({
          endpoint: `bond:${a.index}-${b.index}`,
          x: Math.round((a.x + b.x) / 2),
          y: Math.round((a.y + b.y) / 2),
          type: "bond",
          label: `${a.symbol}\u2013${b.symbol}`,
        });
      }

      prevIndex = atoms.length - 1;
      gIndex += 1;
      slot += 1;
    });
    if (mi < mols.length - 1) slot += 1; // gap slot between molecules
  });

  return { atoms, bonds, anchors, width, height };
}

/** The interactive overlay. Construct once per structure region. */
export class ArrowOverlay {
  /**
   * @param {Element} hostEl   positioned container; the overlay <svg> is appended here.
   * @param {object}  opts
   *   onArrowsChange(arrows) called after a user add/remove (arrows = full list)
   *   onStatus(message)      called with the current picking hint (optional)
   *   viewBox "0 0 W H"      coordinate space (must match the structure layer)
   *   curvature, minBow, hitRadius — see DEFAULTS
   */
  constructor(hostEl, opts = {}) {
    this.host = hostEl;
    this.onArrowsChange = opts.onArrowsChange || null;
    this.onStatus = opts.onStatus || null;
    this.viewW = opts.viewW ?? DEFAULTS.viewW;
    this.viewH = opts.viewH ?? DEFAULTS.viewH;
    this.curvature = opts.curvature ?? DEFAULTS.curvature;
    this.minBow = opts.minBow ?? DEFAULTS.minBow;
    this.hitRadius = opts.hitRadius ?? DEFAULTS.hitRadius;
    this.arrowHitRadius = opts.arrowHitRadius ?? DEFAULTS.arrowHitRadius;

    /** @type {{from:string,to:string,kind:string}[]} SOURCE OF TRUTH */
    this.arrows = [];
    /** @type {{endpoint:string,x:number,y:number,type?:string,label?:string}[]} */
    this.anchors = [];
    this._anchorMap = new Map();

    this.pending = null; // endpoint chosen as source, awaiting the target
    this.hoverEndpoint = null;
    this.selected = -1; // index of a selected arrow (for deletion)
    this.active = opts.active !== false; // pointer-events on/off (off => Ketcher below is usable)

    this.svg = document.createElementNS(SVG_NS, "svg");
    this.svg.setAttribute("class", "mech-arrow-overlay");
    this.svg.setAttribute("viewBox", `0 0 ${this.viewW} ${this.viewH}`);
    this.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.svg.setAttribute("role", "img");
    this.svg.setAttribute("aria-label", "Curved-arrow overlay");
    this.svg.style.touchAction = "none";
    this._applyActive();
    this.host.appendChild(this.svg);

    this._onClick = this._onClick.bind(this);
    this._onMove = this._onMove.bind(this);
    this._onLeave = this._onLeave.bind(this);
    this._onKey = this._onKey.bind(this);
    this.svg.addEventListener("click", this._onClick);
    this.svg.addEventListener("pointermove", this._onMove);
    this.svg.addEventListener("pointerleave", this._onLeave);
    document.addEventListener("keydown", this._onKey);

    this.render();
  }

  // ── public data API (data first) ───────────────────────────────────────────
  /** Replace the anchor set (positions the structure exposes). */
  setAnchors(list) {
    this.anchors = (list || []).slice();
    this._anchorMap = new Map(this.anchors.map((a) => [a.endpoint, a]));
    // Drop a stale pending selection that no longer exists.
    if (this.pending && !this._anchorMap.has(this.pending)) this.pending = null;
    this.render();
  }

  /** Load arrows from data (e.g. a Step). Normalizes; does not fire onArrowsChange. */
  setArrows(list) {
    this.arrows = (list || []).map(normalizeArrow);
    this.selected = -1;
    this.render();
  }

  /** Deep copy of the arrow data. */
  getArrows() {
    return this.arrows.map((a) => ({ from: a.from, to: a.to, kind: a.kind }));
  }

  /** Programmatically add an arrow (used by the keyboard-accessible controls). */
  addArrow(from, to) {
    const a = normalizeArrow({ from, to, kind: "curved" });
    this.arrows.push(a);
    this.pending = null;
    this._emit();
    this.render();
    return a;
  }

  removeArrow(i) {
    if (i >= 0 && i < this.arrows.length) {
      this.arrows.splice(i, 1);
      if (this.selected === i) this.selected = -1;
      this._emit();
      this.render();
    }
  }

  clear() {
    this.arrows = [];
    this.pending = null;
    this.selected = -1;
    this._emit();
    this.render();
  }

  cancelPending() {
    if (this.pending) {
      this.pending = null;
      this._status();
      this.render();
    }
  }

  /** Toggle whether the overlay captures pointer events. */
  setActive(on) {
    this.active = !!on;
    this._applyActive();
  }

  destroy() {
    this.svg.removeEventListener("click", this._onClick);
    this.svg.removeEventListener("pointermove", this._onMove);
    this.svg.removeEventListener("pointerleave", this._onLeave);
    document.removeEventListener("keydown", this._onKey);
    if (this.svg.parentNode) this.svg.parentNode.removeChild(this.svg);
  }

  // ── endpoint -> point resolution (render second) ────────────────────────────
  /**
   * Resolve an endpoint token to an {x,y} in viewBox space, or null if unknown.
   * Direct anchor lookup first; then sensible fallbacks (bond midpoint from its
   * two atoms, lone pair offset from its atom) so arrows still render even when
   * the structure only exposed atom anchors.
   */
  resolve(endpoint) {
    const direct = this._anchorMap.get(endpoint);
    if (direct) return { x: direct.x, y: direct.y };
    if (endpoint.startsWith("bond:")) {
      const [i, j] = endpoint.slice(5).split("-");
      const a = this._anchorMap.get(`atom:${i}`);
      const b = this._anchorMap.get(`atom:${j}`);
      if (a && b) return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    } else if (endpoint.startsWith("lp:")) {
      const a = this._anchorMap.get(`atom:${endpoint.slice(3)}`);
      if (a) return { x: a.x, y: a.y - 26 };
    }
    return null;
  }

  // ── pointer / keyboard interaction ──────────────────────────────────────────
  _svgPoint(evt) {
    const ctm = this.svg.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const pt = this.svg.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    const p = pt.matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  _hitAnchor(p) {
    let best = null;
    let bestD = this.hitRadius;
    for (const a of this.anchors) {
      const d = Math.hypot(p.x - a.x, p.y - a.y);
      if (d <= bestD) {
        bestD = d;
        best = a;
      }
    }
    return best;
  }

  _hitArrow(p) {
    let best = -1;
    let bestD = this.arrowHitRadius;
    for (let i = 0; i < this.arrows.length; i++) {
      const geo = this._arrowGeometry(this.arrows[i]);
      if (!geo) continue;
      const d = this._distToQuadratic(p, geo);
      if (d <= bestD) {
        bestD = d;
        best = i;
      }
    }
    return best;
  }

  _onClick(evt) {
    if (!this.active) return;
    const p = this._svgPoint(evt);
    const anchor = this._hitAnchor(p);

    if (anchor) {
      if (!this.pending) {
        this.pending = anchor.endpoint;
        this.selected = -1;
      } else if (this.pending === anchor.endpoint) {
        this.pending = null; // clicking the source again cancels
      } else {
        this.arrows.push(normalizeArrow({ from: this.pending, to: anchor.endpoint, kind: "curved" }));
        this.pending = null;
        this._emit();
      }
      this._status();
      this.render();
      return;
    }

    // Clicked empty space: (de)select an existing arrow, or cancel a pending pick.
    const hit = this._hitArrow(p);
    if (hit >= 0) {
      this.selected = this.selected === hit ? -1 : hit;
    } else {
      this.pending = null;
      this.selected = -1;
    }
    this._status();
    this.render();
  }

  _onMove(evt) {
    if (!this.active) return;
    const p = this._svgPoint(evt);
    const anchor = this._hitAnchor(p);
    const next = anchor ? anchor.endpoint : null;
    if (next !== this.hoverEndpoint) {
      this.hoverEndpoint = next;
      this.render();
    }
  }

  _onLeave() {
    if (this.hoverEndpoint) {
      this.hoverEndpoint = null;
      this.render();
    }
  }

  _onKey(evt) {
    if (!this.active) return;
    if (evt.key === "Escape" && this.pending) {
      this.cancelPending();
      return;
    }
    if ((evt.key === "Delete" || evt.key === "Backspace") && this.selected >= 0) {
      const t = evt.target;
      const tag = t && t.tagName ? t.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || (t && t.isContentEditable)) return;
      evt.preventDefault();
      this.removeArrow(this.selected);
    }
  }

  _emit() {
    if (typeof this.onArrowsChange === "function") this.onArrowsChange(this.getArrows());
  }

  _status() {
    if (typeof this.onStatus !== "function") return;
    if (this.pending) {
      const a = this._anchorMap.get(this.pending);
      this.onStatus(`From ${a ? a.label || this.pending : this.pending} — now click the target (Esc to cancel).`);
    } else {
      this.onStatus("Click a source atom / bond / lone pair, then its target.");
    }
  }

  // ── geometry ────────────────────────────────────────────────────────────────
  /** Compute {sx,sy,cx,cy,tx,ty} for an arrow, or null if unresolvable. */
  _arrowGeometry(arrow) {
    const s = this.resolve(arrow.from);
    const t = this.resolve(arrow.to);
    if (!s || !t) return null;
    const mx = (s.x + t.x) / 2;
    const my = (s.y + t.y) / 2;
    let dx = t.x - s.x;
    let dy = t.y - s.y;
    const len = Math.hypot(dx, dy) || 1;
    // Perpendicular unit vector; bow the curve to one side.
    const nx = -dy / len;
    const ny = dx / len;
    const bow = Math.max(this.minBow, len * this.curvature);
    return { sx: s.x, sy: s.y, cx: mx + nx * bow, cy: my + ny * bow, tx: t.x, ty: t.y };
  }

  _distToQuadratic(p, geo) {
    // Sample the Bézier and take the min point-distance (good enough for hit-testing).
    let best = Infinity;
    const N = 16;
    for (let k = 0; k <= N; k++) {
      const u = k / N;
      const iu = 1 - u;
      const x = iu * iu * geo.sx + 2 * iu * u * geo.cx + u * u * geo.tx;
      const y = iu * iu * geo.sy + 2 * iu * u * geo.cy + u * u * geo.ty;
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < best) best = d;
    }
    return best;
  }

  // ── rendering (pure function of arrows + anchors) ───────────────────────────
  render() {
    const parts = [];
    parts.push(
      `<defs>` +
        `<marker id="mech-arrowhead" markerWidth="12" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse">` +
        `<path d="M0,0 L11,5 L0,10 L3,5 Z" fill="currentColor"/></marker>` +
        `<marker id="mech-arrowhead-sel" markerWidth="12" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse">` +
        `<path d="M0,0 L11,5 L0,10 L3,5 Z" fill="#dc2626"/></marker>` +
        `</defs>`
    );

    // Anchor affordances: reveal clickable bond/lone-pair points (atoms are drawn
    // by the structure layer beneath). Hover + pending get a highlight ring.
    for (const a of this.anchors) {
      const hovered = a.endpoint === this.hoverEndpoint;
      const isPending = a.endpoint === this.pending;
      if (isPending) {
        parts.push(`<circle cx="${a.x}" cy="${a.y}" r="14" class="mech-anchor-pending"/>`);
      } else if (hovered) {
        parts.push(`<circle cx="${a.x}" cy="${a.y}" r="13" class="mech-anchor-hover"/>`);
      }
      if (a.type === "bond") {
        parts.push(`<circle cx="${a.x}" cy="${a.y}" r="4" class="mech-anchor mech-anchor-bond"/>`);
      } else if (a.type === "lp") {
        parts.push(`<circle cx="${a.x - 3}" cy="${a.y}" r="2.4" class="mech-anchor mech-anchor-lp"/>`);
        parts.push(`<circle cx="${a.x + 3}" cy="${a.y}" r="2.4" class="mech-anchor mech-anchor-lp"/>`);
      } else {
        parts.push(`<circle cx="${a.x}" cy="${a.y}" r="3" class="mech-anchor mech-anchor-atom"/>`);
      }
    }

    // Arrows (data -> curves). Unresolvable arrows are skipped, never dropped.
    let unresolved = 0;
    this.arrows.forEach((arrow, i) => {
      const geo = this._arrowGeometry(arrow);
      if (!geo) {
        unresolved += 1;
        return;
      }
      const sel = i === this.selected;
      const cls = sel ? "mech-arrow mech-arrow-selected" : "mech-arrow";
      const marker = sel ? "url(#mech-arrowhead-sel)" : "url(#mech-arrowhead)";
      parts.push(
        `<path class="${cls}" d="M ${geo.sx.toFixed(1)} ${geo.sy.toFixed(1)} Q ${geo.cx.toFixed(1)} ${geo.cy.toFixed(
          1
        )} ${geo.tx.toFixed(1)} ${geo.ty.toFixed(1)}" fill="none" marker-end="${marker}"/>`
      );
    });

    if (unresolved > 0) {
      parts.push(
        `<text x="${this.viewW - 8}" y="18" text-anchor="end" class="mech-arrow-note">` +
          `${unresolved} arrow${unresolved > 1 ? "s" : ""} stored (endpoint off-structure)</text>`
      );
    }

    this.svg.innerHTML = parts.join("");
  }

  _applyActive() {
    this.svg.style.pointerEvents = this.active ? "auto" : "none";
  }
}

export default ArrowOverlay;
