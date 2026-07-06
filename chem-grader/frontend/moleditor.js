/*
 * moleditor.js — a self-contained SVG structure editor (MoleculeEditor).
 *
 * new MoleculeEditor(svgEl, onChange)
 *   Draw atoms/bonds (skeletal), wedge/hash stereo bonds, formal charges,
 *   reaction arrows and reagent text on a fixed 960x560 viewBox. The single
 *   source of truth is `mol = { atoms, bonds, arrows, texts }`.
 *
 * Depends on window.Chem (chem.js) for implicit-hydrogen counts in labels.
 * Exposes window.MoleculeEditor.
 */
(function () {
  "use strict";

  const ED = {
    W: 960,
    H: 560,
    BOND_LEN: 55,
    SNAP_DEG: 15,
    HIT_ATOM: 13,
    HIT_BOND: 7,
    HIT_ARROW: 9,
    DRAG_MIN: 5,
    LABEL_TRIM: 11,
  };

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
  const UNKNOWN_COLOR = "#7b1fa2";
  const INK = "#1f2328";
  const ACCENT = "#2563eb"; // matches theme.css --accent
  // NOTE: single quotes inside — this string is injected into double-quoted SVG
  // attributes, and embedded double quotes would break serialization/rasterization.
  const FONT = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";

  const R = Math.round;
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  function distToSeg(p, a, b) {
    const vx = b.x - a.x,
      vy = b.y - a.y;
    const wx = p.x - a.x,
      wy = p.y - a.y;
    const len2 = vx * vx + vy * vy;
    let t = len2 ? (wx * vx + wy * vy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    const cx = a.x + t * vx,
      cy = a.y + t * vy;
    return Math.hypot(p.x - cx, p.y - cy);
  }

  function escapeXml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  const SUB = { "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉" };
  const subscript = (n) => String(n).split("").map((c) => SUB[c] || c).join("");

  const HOVER_TOOLS = new Set(["draw", "wedge", "hash", "select", "erase", "plus", "minus"]);

  class MoleculeEditor {
    constructor(svgEl, onChange) {
      this.svg = svgEl;
      this.onChange = onChange || null;
      this.mol = { atoms: [], bonds: [], arrows: [], texts: [] };
      this.nextId = 1;
      this.tool = "draw";
      this.element = "C";
      this.undoStack = [];
      this.down = null;
      this.preview = null;
      this.hover = null;
      this.activeInput = null;

      this.svg.setAttribute("viewBox", `0 0 ${ED.W} ${ED.H}`);
      this._onDown = this._onDown.bind(this);
      this._onMove = this._onMove.bind(this);
      this._onUp = this._onUp.bind(this);
      this._onKey = this._onKey.bind(this);
      this.svg.addEventListener("pointerdown", this._onDown);
      this.svg.addEventListener("pointermove", this._onMove);
      this.svg.addEventListener("pointerup", this._onUp);
      this.svg.addEventListener("pointercancel", this._onUp);
      document.addEventListener("keydown", this._onKey);

      this.render();
    }

    // ---- public API ---- //
    id() {
      return this.nextId++;
    }

    getMol() {
      return JSON.parse(JSON.stringify(this.mol));
    }

    loadMol(m) {
      const src = m || {};
      const idmap = new Map();
      const atoms = (src.atoms || []).map((a) => {
        const nid = this.id();
        idmap.set(a.id, nid);
        return { id: nid, x: a.x, y: a.y, el: a.el || "C", charge: a.charge || 0 };
      });
      const bonds = (src.bonds || [])
        .filter((b) => idmap.has(b.a) && idmap.has(b.b))
        .map((b) => ({ id: this.id(), a: idmap.get(b.a), b: idmap.get(b.b), order: b.order || 1, style: b.style || "plain" }));
      const arrows = (src.arrows || []).map((a) => ({ id: this.id(), x1: a.x1, y1: a.y1, x2: a.x2, y2: a.y2 }));
      const texts = (src.texts || []).map((t) => ({ id: this.id(), x: t.x, y: t.y, str: t.str || "" }));
      this.mol = { atoms, bonds, arrows, texts };
      this.undoStack = [];
      this.emitChange();
    }

    undo() {
      if (!this.undoStack.length) return;
      this.mol = JSON.parse(this.undoStack.pop());
      this.emitChange();
    }

    clear() {
      if (!this.mol.atoms.length && !this.mol.arrows.length && !this.mol.texts.length) return;
      this.pushUndo();
      this.mol = { atoms: [], bonds: [], arrows: [], texts: [] };
      this.emitChange();
    }

    // ---- internals ---- //
    pushUndo() {
      this.undoStack.push(JSON.stringify(this.mol));
      if (this.undoStack.length > 100) this.undoStack.shift();
    }

    emitChange() {
      this.render();
      if (typeof this.onChange === "function") this.onChange();
    }

    svgPoint(e) {
      const ctm = this.svg.getScreenCTM();
      if (!ctm) return { x: 0, y: 0 };
      const pt = this.svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const p = pt.matrixTransform(ctm.inverse());
      return { x: p.x, y: p.y };
    }

    atomById(id) {
      return this.mol.atoms.find((a) => a.id === id) || null;
    }

    bondCount(id) {
      let n = 0;
      for (const b of this.mol.bonds) if (b.a === id || b.b === id) n++;
      return n;
    }

    orderSum(id) {
      let s = 0;
      for (const b of this.mol.bonds) if (b.a === id || b.b === id) s += b.order || 1;
      return s;
    }

    showLabel(atom) {
      return atom.el !== "C" || this.bondCount(atom.id) === 0;
    }

    hitAtom(p, excludeId) {
      let best = null,
        bestD = ED.HIT_ATOM;
      for (const a of this.mol.atoms) {
        if (excludeId != null && a.id === excludeId) continue;
        const d = dist(p, a);
        if (d <= bestD) {
          bestD = d;
          best = a;
        }
      }
      return best;
    }

    hitBond(p) {
      for (let i = this.mol.bonds.length - 1; i >= 0; i--) {
        const b = this.mol.bonds[i];
        const A = this.atomById(b.a),
          B = this.atomById(b.b);
        if (A && B && distToSeg(p, A, B) < ED.HIT_BOND) return b;
      }
      return null;
    }

    hitArrow(p) {
      for (let i = this.mol.arrows.length - 1; i >= 0; i--) {
        const a = this.mol.arrows[i];
        if (distToSeg(p, { x: a.x1, y: a.y1 }, { x: a.x2, y: a.y2 }) < ED.HIT_ARROW) return a;
      }
      return null;
    }

    hitText(p) {
      for (let i = this.mol.texts.length - 1; i >= 0; i--) {
        const t = this.mol.texts[i];
        const w = Math.max(12, (t.str || "").length * 8);
        if (p.x >= t.x - 6 && p.x <= t.x + w + 6 && Math.abs(p.y - t.y) <= 11) return t;
      }
      return null;
    }

    snapFrom(atom, p) {
      const onto = this.hitAtom(p, atom.id);
      if (onto) return { toAtom: onto, x: onto.x, y: onto.y };
      let ang = Math.atan2(p.y - atom.y, p.x - atom.x);
      const step = (ED.SNAP_DEG * Math.PI) / 180;
      ang = Math.round(ang / step) * step;
      return { toAtom: null, x: R(atom.x + ED.BOND_LEN * Math.cos(ang)), y: R(atom.y + ED.BOND_LEN * Math.sin(ang)) };
    }

    // ---- pointer state machine ---- //
    _onDown(e) {
      if (this.activeInput) return; // an inline text input is open
      if (e.button != null && e.button !== 0) return;
      const p = this.svgPoint(e);
      const a = this.hitAtom(p);
      const b = a ? null : this.hitBond(p);
      const d = { start: p, moved: false, snapshotPushed: false, grab: p };

      switch (this.tool) {
        case "draw":
        case "wedge":
        case "hash":
          if (a) {
            d.mode = "bondDrag";
            d.from = a;
          } else if (b) {
            d.mode = "bondClick";
            d.bond = b;
          } else {
            d.mode = "emptyClick";
          }
          break;
        case "select": {
          if (a) {
            d.mode = "moveAtom";
            d.atom = a;
            d.orig = { x: a.x, y: a.y };
          } else {
            const t = this.hitText(p);
            const ar = t ? null : this.hitArrow(p);
            if (t) {
              d.mode = "moveText";
              d.textObj = t;
              d.orig = { x: t.x, y: t.y };
            } else if (ar) {
              d.mode = "moveArrow";
              d.arrow = ar;
              d.orig = { x1: ar.x1, y1: ar.y1, x2: ar.x2, y2: ar.y2 };
            } else {
              d.mode = "none";
            }
          }
          break;
        }
        case "erase":
          d.mode = "erase";
          break;
        case "plus":
        case "minus":
          if (a) {
            d.mode = "charge";
            d.atom = a;
            d.dir = this.tool === "plus" ? 1 : -1;
          } else {
            d.mode = "none";
          }
          break;
        case "arrow":
          d.mode = "arrowDrag";
          d.from = p;
          break;
        case "text":
          d.mode = "text";
          break;
        default:
          d.mode = "none";
      }

      this.down = d;
      this.hover = null;
      try {
        this.svg.setPointerCapture(e.pointerId);
      } catch (_) {}
    }

    _onMove(e) {
      const p = this.svgPoint(e);
      if (!this.down) {
        this._hoverMove(p);
        return;
      }
      const d = this.down;
      if (dist(p, d.start) > ED.DRAG_MIN) d.moved = true;

      switch (d.mode) {
        case "bondDrag": {
          const snap = this.snapFrom(d.from, p);
          const style = this.tool === "wedge" ? "wedge" : this.tool === "hash" ? "hash" : "plain";
          this.preview = { kind: "bond", from: d.from, to: { x: snap.x, y: snap.y }, onAtom: !!snap.toAtom, style };
          this.render();
          break;
        }
        case "arrowDrag": {
          let y = p.y;
          if (Math.abs(p.y - d.from.y) < 14) y = d.from.y; // snap to horizontal
          this.preview = { kind: "arrow", x1: d.from.x, y1: d.from.y, x2: p.x, y2: y };
          this.render();
          break;
        }
        case "moveAtom": {
          if (!d.snapshotPushed) {
            this.pushUndo();
            d.snapshotPushed = true;
          }
          d.atom.x = R(d.orig.x + (p.x - d.grab.x));
          d.atom.y = R(d.orig.y + (p.y - d.grab.y));
          this.emitChange();
          break;
        }
        case "moveText": {
          if (!d.snapshotPushed) {
            this.pushUndo();
            d.snapshotPushed = true;
          }
          d.textObj.x = R(d.orig.x + (p.x - d.grab.x));
          d.textObj.y = R(d.orig.y + (p.y - d.grab.y));
          this.emitChange();
          break;
        }
        case "moveArrow": {
          if (!d.snapshotPushed) {
            this.pushUndo();
            d.snapshotPushed = true;
          }
          const dx = p.x - d.grab.x,
            dy = p.y - d.grab.y;
          d.arrow.x1 = R(d.orig.x1 + dx);
          d.arrow.y1 = R(d.orig.y1 + dy);
          d.arrow.x2 = R(d.orig.x2 + dx);
          d.arrow.y2 = R(d.orig.y2 + dy);
          this.emitChange();
          break;
        }
        default:
          break;
      }
    }

    _onUp(e) {
      if (!this.down) return;
      const d = this.down;
      this.down = null;
      this.preview = null;
      try {
        this.svg.releasePointerCapture(e.pointerId);
      } catch (_) {}
      const p = this.svgPoint(e);

      switch (d.mode) {
        case "emptyClick":
          if (!d.moved) {
            this.pushUndo();
            this.mol.atoms.push({ id: this.id(), x: R(d.start.x), y: R(d.start.y), el: this.element, charge: 0 });
            this.emitChange();
          } else {
            this.render();
          }
          break;

        case "bondDrag": {
          if (!d.moved) {
            // relabel the from-atom to the current element
            if (d.from.el !== this.element) {
              this.pushUndo();
              d.from.el = this.element;
              this.emitChange();
            } else {
              this.render();
            }
            break;
          }
          const snap = this.snapFrom(d.from, p);
          let to = snap.toAtom;
          this.pushUndo();
          if (!to) {
            // New terminus takes the currently selected element (C by default,
            // which renders as a bare skeletal vertex).
            to = { id: this.id(), x: snap.x, y: snap.y, el: this.element, charge: 0 };
            this.mol.atoms.push(to);
          }
          if (to.id === d.from.id) {
            this.undoStack.pop();
            this.render();
            break;
          }
          const existing = this.mol.bonds.find(
            (bd) => (bd.a === d.from.id && bd.b === to.id) || (bd.a === to.id && bd.b === d.from.id)
          );
          if (existing) {
            existing.order = existing.order >= 3 ? 1 : existing.order + 1;
            if (existing.order > 1) existing.style = "plain";
          } else {
            const style = this.tool === "wedge" ? "wedge" : this.tool === "hash" ? "hash" : "plain";
            this.mol.bonds.push({ id: this.id(), a: d.from.id, b: to.id, order: 1, style });
          }
          this.emitChange();
          break;
        }

        case "bondClick": {
          this.pushUndo();
          const bond = d.bond;
          if (this.tool === "draw") {
            bond.order = bond.order >= 3 ? 1 : bond.order + 1;
            if (bond.order > 1) bond.style = "plain";
          } else {
            const want = this.tool === "wedge" ? "wedge" : "hash";
            if (bond.style === want) {
              const t = bond.a;
              bond.a = bond.b;
              bond.b = t; // flip wedge/hash direction
            } else {
              bond.style = want;
              bond.order = 1;
            }
          }
          this.emitChange();
          break;
        }

        case "erase": {
          const removed = this._eraseAt(d.start);
          if (removed) this.emitChange();
          else this.render();
          break;
        }

        case "charge": {
          if (!d.moved) {
            this.pushUndo();
            d.atom.charge = Math.max(-3, Math.min(3, (d.atom.charge || 0) + d.dir));
            this.emitChange();
          } else {
            this.render();
          }
          break;
        }

        case "arrowDrag": {
          if (d.moved) {
            let y2 = p.y;
            if (Math.abs(p.y - d.from.y) < 14) y2 = d.from.y;
            const len = Math.hypot(p.x - d.from.x, y2 - d.from.y);
            if (len > 25) {
              this.pushUndo();
              this.mol.arrows.push({ id: this.id(), x1: R(d.from.x), y1: R(d.from.y), x2: R(p.x), y2: R(y2) });
              this.emitChange();
              break;
            }
          }
          this.render();
          break;
        }

        case "text": {
          if (!d.moved) {
            const t = this.hitText(d.start);
            this.openTextInput(t ? t.x : d.start.x, t ? t.y : d.start.y, t || null);
          } else {
            this.render();
          }
          break;
        }

        default:
          this.render();
      }
    }

    _eraseAt(p) {
      const a = this.hitAtom(p);
      if (a) {
        this.pushUndo();
        this.mol.bonds = this.mol.bonds.filter((b) => b.a !== a.id && b.b !== a.id);
        this.mol.atoms = this.mol.atoms.filter((x) => x.id !== a.id);
        return true;
      }
      const b = this.hitBond(p);
      if (b) {
        this.pushUndo();
        this.mol.bonds = this.mol.bonds.filter((x) => x.id !== b.id);
        return true;
      }
      const t = this.hitText(p);
      if (t) {
        this.pushUndo();
        this.mol.texts = this.mol.texts.filter((x) => x.id !== t.id);
        return true;
      }
      const ar = this.hitArrow(p);
      if (ar) {
        this.pushUndo();
        this.mol.arrows = this.mol.arrows.filter((x) => x.id !== ar.id);
        return true;
      }
      return false;
    }

    _hoverMove(p) {
      if (!HOVER_TOOLS.has(this.tool)) {
        if (this.hover) {
          this.hover = null;
          this.render();
        }
        return;
      }
      const a = this.hitAtom(p);
      const b = a ? null : this.hitBond(p);
      const next = a ? { atomId: a.id } : b ? { bondId: b.id } : null;
      const same =
        (!next && !this.hover) ||
        (next && this.hover && next.atomId === this.hover.atomId && next.bondId === this.hover.bondId);
      if (!same) {
        this.hover = next;
        this.render();
      }
    }

    _onKey(e) {
      if (this.activeInput) return;
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        this.undo();
      }
    }

    // ---- inline text input ---- //
    openTextInput(x, y, textObj) {
      this._removeInput();
      const input = document.createElement("input");
      input.type = "text";
      input.className = "inline-text";
      input.value = textObj ? textObj.str : "";
      const rect = this.svg.getBoundingClientRect();
      const sx = rect.width / ED.W,
        sy = rect.height / ED.H;
      input.style.position = "fixed";
      input.style.left = rect.left + x * sx + "px";
      input.style.top = rect.top + y * sy - 13 + "px";
      document.body.appendChild(input);
      this.activeInput = input;
      input.focus();
      input.select();

      let done = false;
      const finish = (commit) => {
        if (done) return;
        done = true;
        const val = input.value.trim();
        this._removeInput();
        if (!commit) return;
        if (textObj) {
          if (!val) {
            this.pushUndo();
            this.mol.texts = this.mol.texts.filter((t) => t.id !== textObj.id);
            this.emitChange();
          } else if (val !== textObj.str) {
            this.pushUndo();
            textObj.str = val;
            this.emitChange();
          }
        } else if (val) {
          this.pushUndo();
          this.mol.texts.push({ id: this.id(), x: R(x), y: R(y), str: val });
          this.emitChange();
        }
      };
      input.addEventListener("keydown", (ev) => {
        ev.stopPropagation();
        if (ev.key === "Enter") {
          ev.preventDefault();
          finish(true);
        } else if (ev.key === "Escape") {
          ev.preventDefault();
          finish(false);
        }
      });
      input.addEventListener("blur", () => finish(true));
    }

    _removeInput() {
      if (this.activeInput && this.activeInput.parentNode) {
        this.activeInput.parentNode.removeChild(this.activeInput);
      }
      this.activeInput = null;
    }

    // ---- rendering ---- //
    render() {
      const parts = [];
      parts.push(
        `<defs>` +
          `<marker id="arrowhead" markerWidth="10" markerHeight="8" refX="8.5" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,4 L0,8 Z" fill="${INK}"/></marker>` +
          `<marker id="arrowhead-accent" markerWidth="10" markerHeight="8" refX="8.5" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,4 L0,8 Z" fill="${ACCENT}"/></marker>` +
          `</defs>`
      );
      parts.push(`<rect x="0" y="0" width="${ED.W}" height="${ED.H}" fill="#ffffff"/>`);

      // hover highlight (under the structure)
      if (this.hover) {
        if (this.hover.atomId != null) {
          const a = this.atomById(this.hover.atomId);
          if (a) parts.push(`<circle cx="${a.x}" cy="${a.y}" r="12" fill="${ACCENT}" opacity="0.18"/>`);
        } else if (this.hover.bondId != null) {
          const b = this.mol.bonds.find((x) => x.id === this.hover.bondId);
          const A = b && this.atomById(b.a),
            B = b && this.atomById(b.b);
          if (A && B)
            parts.push(
              `<line x1="${A.x}" y1="${A.y}" x2="${B.x}" y2="${B.y}" stroke="${ACCENT}" stroke-width="8" stroke-linecap="round" opacity="0.18"/>`
            );
        }
      }

      // bonds
      for (const b of this.mol.bonds) {
        const A = this.atomById(b.a),
          B = this.atomById(b.b);
        if (A && B) parts.push(this.renderBond(A, B, b, this.showLabel(A), this.showLabel(B)));
      }

      // atom labels + charges
      for (const a of this.mol.atoms) {
        if (this.showLabel(a)) parts.push(this.renderLabel(a));
        if (a.charge) parts.push(this.renderCharge(a));
      }

      // arrows
      for (const ar of this.mol.arrows) {
        parts.push(
          `<line x1="${ar.x1}" y1="${ar.y1}" x2="${ar.x2}" y2="${ar.y2}" stroke="${INK}" stroke-width="2" marker-end="url(#arrowhead)"/>`
        );
      }

      // texts
      for (const t of this.mol.texts) {
        parts.push(
          `<text x="${t.x}" y="${t.y}" font-family="${FONT}" font-size="16" fill="${INK}" dominant-baseline="central" style="paint-order:stroke" stroke="#fff" stroke-width="3">${escapeXml(
            t.str
          )}</text>`
        );
      }

      // live preview
      if (this.preview) parts.push(this.renderPreview(this.preview));

      this.svg.innerHTML = parts.join("");
    }

    renderBond(A, B, bond, labelA, labelB) {
      const dx = B.x - A.x,
        dy = B.y - A.y;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len,
        uy = dy / len;
      const px = -uy,
        py = ux;
      let ax = A.x,
        ay = A.y,
        bx = B.x,
        by = B.y;
      if (labelA) {
        ax += ux * ED.LABEL_TRIM;
        ay += uy * ED.LABEL_TRIM;
      }
      if (labelB) {
        bx -= ux * ED.LABEL_TRIM;
        by -= uy * ED.LABEL_TRIM;
      }
      const line = (x1, y1, x2, y2, w) =>
        `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${INK}" stroke-width="${w}" stroke-linecap="round"/>`;

      if (bond.style === "wedge") {
        const w = 5;
        const p1 = `${ax.toFixed(1)},${ay.toFixed(1)}`;
        const p2 = `${(bx + px * w).toFixed(1)},${(by + py * w).toFixed(1)}`;
        const p3 = `${(bx - px * w).toFixed(1)},${(by - py * w).toFixed(1)}`;
        return `<polygon points="${p1} ${p2} ${p3}" fill="${INK}"/>`;
      }
      if (bond.style === "hash") {
        const segLen = Math.hypot(bx - ax, by - ay);
        const n = Math.max(4, Math.round(segLen / 6));
        let out = "";
        for (let i = 0; i < n; i++) {
          const t = n === 1 ? 0 : i / (n - 1);
          const cx = ax + (bx - ax) * t;
          const cy = ay + (by - ay) * t;
          const hw = 1.5 + (5.5 - 1.5) * t;
          out += line(cx + px * hw, cy + py * hw, cx - px * hw, cy - py * hw, 1.6);
        }
        return out;
      }
      if (bond.order === 2) {
        const o = 2.6;
        return line(ax + px * o, ay + py * o, bx + px * o, by + py * o, 1.8) + line(ax - px * o, ay - py * o, bx - px * o, by - py * o, 1.8);
      }
      if (bond.order === 3) {
        const o = 4.4;
        return (
          line(ax, ay, bx, by, 1.8) +
          line(ax + px * o, ay + py * o, bx + px * o, by + py * o, 1.6) +
          line(ax - px * o, ay - py * o, bx - px * o, by - py * o, 1.6)
        );
      }
      return line(ax, ay, bx, by, 1.9);
    }

    renderLabel(a) {
      const color = EL_COLORS[a.el] || UNKNOWN_COLOR;
      const h = window.Chem ? window.Chem.implicitHydrogens(a, this.orderSum(a.id)) : 0;
      let inner = escapeXml(a.el);
      if (h === 1) inner += "H";
      else if (h > 1) inner += "H" + subscript(h);
      return (
        `<text x="${a.x}" y="${a.y}" text-anchor="middle" dominant-baseline="central" font-family="${FONT}" ` +
        `font-size="19" font-weight="600" fill="${color}" stroke="#fff" stroke-width="3.5" style="paint-order:stroke">${inner}</text>`
      );
    }

    renderCharge(a) {
      const mag = Math.abs(a.charge);
      const sign = a.charge > 0 ? "+" : "−";
      const label = (mag > 1 ? mag : "") + sign;
      return (
        `<text x="${a.x + 11}" y="${a.y - 11}" text-anchor="middle" dominant-baseline="central" font-family="${FONT}" ` +
        `font-size="14" font-weight="700" fill="${ACCENT}" stroke="#fff" stroke-width="3" style="paint-order:stroke">${label}</text>`
      );
    }

    renderPreview(pv) {
      if (pv.kind === "bond") {
        const A = pv.from,
          T = pv.to;
        let out = `<line x1="${A.x}" y1="${A.y}" x2="${T.x}" y2="${T.y}" stroke="${ACCENT}" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round"/>`;
        if (!pv.onAtom) out += `<circle cx="${T.x}" cy="${T.y}" r="3.5" fill="${ACCENT}"/>`;
        return out;
      }
      if (pv.kind === "arrow") {
        return `<line x1="${pv.x1}" y1="${pv.y1}" x2="${pv.x2}" y2="${pv.y2}" stroke="${ACCENT}" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#arrowhead-accent)"/>`;
      }
      return "";
    }
  }

  MoleculeEditor.ED = ED;
  MoleculeEditor.EL_COLORS = EL_COLORS;
  window.MoleculeEditor = MoleculeEditor;
})();
