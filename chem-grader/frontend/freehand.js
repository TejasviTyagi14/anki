/*
 * freehand.js — a pressure-aware ink canvas (FreehandCanvas).
 *
 * new FreehandCanvas(canvasEl, onChange)
 *   Draw freehand strokes with a mouse, finger, or stylus (Apple Pencil). Pen /
 *   eraser tools, stroke-level undo, clear. Strokes are stored as vectors in a
 *   fixed 960x560 logical space (resolution-independent, so they can be saved to
 *   localStorage) and rasterized to a crisp white-background PNG for grading.
 *
 * Exposes window.FreehandCanvas.
 */
(function () {
  "use strict";

  const W = 960;
  const H = 560;
  const SCALE = 2; // internal supersampling for crisp ink

  class FreehandCanvas {
    constructor(canvasEl, onChange) {
      this.canvas = canvasEl;
      this.onChange = onChange || null;
      this.canvas.width = W * SCALE;
      this.canvas.height = H * SCALE;
      this.ctx = this.canvas.getContext("2d");
      this.tool = "pen";
      this.width = 3.2; // logical px (pen)
      this.eraserWidth = 22;
      this.color = "#13233d";
      this.strokes = [];
      this.current = null;
      this.drawing = false;

      this._down = this._down.bind(this);
      this._move = this._move.bind(this);
      this._up = this._up.bind(this);
      this.canvas.addEventListener("pointerdown", this._down);
      // listen on window so a stroke keeps going if the pointer leaves the canvas
      window.addEventListener("pointermove", this._move);
      window.addEventListener("pointerup", this._up);
      window.addEventListener("pointercancel", this._up);

      this.redraw();
    }

    // ---- public API ----
    setTool(t) {
      this.tool = t;
    }
    setWidth(w) {
      this.width = w;
    }
    isEmpty() {
      return this.strokes.length === 0;
    }
    getStrokes() {
      return this.strokes;
    }
    loadStrokes(arr) {
      this.strokes = Array.isArray(arr) ? arr : [];
      this.current = null;
      this.drawing = false;
      this.redraw();
    }
    undo() {
      if (!this.strokes.length) return;
      this.strokes.pop();
      this.redraw();
      this._emit();
    }
    clear() {
      if (!this.strokes.length) return;
      this.strokes = [];
      this.redraw();
      this._emit();
    }
    toPngBase64() {
      return this.canvas.toDataURL("image/png").split(",")[1];
    }

    // ---- pointer handling ----
    _pt(e) {
      const r = this.canvas.getBoundingClientRect();
      return {
        x: ((e.clientX - r.left) / r.width) * W,
        y: ((e.clientY - r.top) / r.height) * H,
        p: e.pressure && e.pressure > 0 ? e.pressure : 0.5,
      };
    }

    _down(e) {
      if (e.button != null && e.button !== 0) return;
      e.preventDefault();
      this.drawing = true;
      try {
        this.canvas.setPointerCapture(e.pointerId);
      } catch (_) {}
      const eraser = this.tool === "eraser";
      this.current = {
        color: eraser ? "#ffffff" : this.color,
        width: eraser ? this.eraserWidth : this.width,
        points: [this._pt(e)],
      };
    }

    _move(e) {
      if (!this.drawing || !this.current) return;
      const pt = this._pt(e);
      const pts = this.current.points;
      const last = pts[pts.length - 1];
      if (Math.hypot(pt.x - last.x, pt.y - last.y) < 0.6) return;
      pts.push(pt);
      this._segment(last, pt, this.current); // incremental draw
    }

    _up() {
      if (!this.drawing) return;
      this.drawing = false;
      if (this.current && this.current.points.length) {
        if (this.current.points.length === 1) {
          const p0 = this.current.points[0];
          this.current.points.push({ x: p0.x + 0.5, y: p0.y + 0.5, p: p0.p }); // render a dot
        }
        this.strokes.push(this.current);
      }
      this.current = null;
      this.redraw();
      this._emit();
    }

    _emit() {
      if (typeof this.onChange === "function") this.onChange();
    }

    // ---- drawing ----
    _segment(a, b, s) {
      const c = this.ctx;
      c.lineJoin = "round";
      c.lineCap = "round";
      c.strokeStyle = s.color;
      c.lineWidth = s.width * (0.55 + 0.9 * ((a.p + b.p) / 2)) * SCALE;
      c.beginPath();
      c.moveTo(a.x * SCALE, a.y * SCALE);
      c.lineTo(b.x * SCALE, b.y * SCALE);
      c.stroke();
    }

    _drawStroke(s) {
      const pts = s.points;
      for (let i = 1; i < pts.length; i++) this._segment(pts[i - 1], pts[i], s);
    }

    redraw() {
      const c = this.ctx;
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, this.canvas.width, this.canvas.height);
      c.fillStyle = "#ffffff";
      c.fillRect(0, 0, this.canvas.width, this.canvas.height);
      for (const s of this.strokes) this._drawStroke(s);
    }
  }

  window.FreehandCanvas = FreehandCanvas;
})();
