// Shared handwriting pad + recognizer used by the standalone checker and the
// flashcard reviewer. Loaded as a classic script; exposes globals on window.

(function () {
  // A drawing surface backed by a <canvas>. Captures mouse / trackpad / touch /
  // stylus via Pointer Events, supports undo + clear, and can load an imported
  // image (e.g. a photo of an iPad drawing) in place of freehand strokes.
  class HandwritingPad {
    constructor(canvas, { onFirstInk } = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.onFirstInk = onFirstInk || (() => {});
      this.penSize = 8;
      this.drawing = false;
      this.lastPoint = null;
      this.hasInk = false;
      this.undoStack = [];
      this.importedSource = null;
      this._reset();
      this._bind();
    }

    _reset() {
      const { ctx, canvas } = this;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#12161c";
    }

    _point(evt) {
      const rect = this.canvas.getBoundingClientRect();
      return {
        x: (evt.clientX - rect.left) * (this.canvas.width / rect.width),
        y: (evt.clientY - rect.top) * (this.canvas.height / rect.height),
      };
    }

    _bind() {
      const c = this.canvas;
      c.addEventListener("pointerdown", (e) => {
        c.setPointerCapture(e.pointerId);
        this._begin(e);
      });
      c.addEventListener("pointermove", (e) => this._move(e));
      ["pointerup", "pointercancel", "pointerleave"].forEach((ev) =>
        c.addEventListener(ev, () => this._end())
      );
    }

    _begin(evt) {
      if (this.importedSource) this.clear();
      this.drawing = true;
      this.undoStack.push(
        this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height)
      );
      if (this.undoStack.length > 40) this.undoStack.shift();
      const p = this._point(evt);
      this.lastPoint = p;
      this.ctx.beginPath();
      this.ctx.fillStyle = "#12161c";
      this.ctx.arc(p.x, p.y, this.penSize / 2, 0, Math.PI * 2);
      this.ctx.fill();
      this._markInk();
    }

    _move(evt) {
      if (!this.drawing) return;
      const events = evt.getCoalescedEvents ? evt.getCoalescedEvents() : [evt];
      this.ctx.lineWidth = this.penSize;
      this.ctx.beginPath();
      this.ctx.moveTo(this.lastPoint.x, this.lastPoint.y);
      for (const e of events) {
        const cp = this._point(e);
        this.ctx.lineTo(cp.x, cp.y);
        this.lastPoint = cp;
      }
      this.ctx.stroke();
    }

    _end() {
      this.drawing = false;
      this.lastPoint = null;
    }

    _markInk() {
      if (!this.hasInk) this.onFirstInk();
      this.hasInk = true;
    }

    setPenSize(n) {
      this.penSize = Number(n);
    }

    clear() {
      this.importedSource = null;
      this.undoStack.length = 0;
      this._reset();
      this.hasInk = false;
    }

    undo() {
      if (this.importedSource) {
        this.clear();
        return;
      }
      const snap = this.undoStack.pop();
      if (snap) {
        this.ctx.putImageData(snap, 0, 0);
        if (this.undoStack.length === 0) this.hasInk = false;
      }
    }

    loadImageFile(file) {
      return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
          this.importedSource = img;
          // Draw the image scaled into the pad so it is visible + recognizable.
          this._reset();
          const scale = Math.min(
            this.canvas.width / img.naturalWidth,
            this.canvas.height / img.naturalHeight
          );
          const w = img.naturalWidth * scale;
          const h = img.naturalHeight * scale;
          this.ctx.drawImage(img, (this.canvas.width - w) / 2, (this.canvas.height - h) / 2, w, h);
          this._markInk();
          resolve();
        };
        img.onerror = reject;
        img.src = url;
      });
    }

    // Composite onto white (and upscale) so the recognizer sees crisp dark ink
    // on a light field. Upscaling meaningfully improves Tesseract accuracy on
    // the relatively small handwriting we capture.
    renderForOcr(scale = 2) {
      const out = document.createElement("canvas");
      out.width = this.canvas.width * scale;
      out.height = this.canvas.height * scale;
      const octx = out.getContext("2d");
      octx.fillStyle = "#ffffff";
      octx.fillRect(0, 0, out.width, out.height);
      octx.imageSmoothingEnabled = true;
      octx.imageSmoothingQuality = "high";
      octx.drawImage(this.canvas, 0, 0, out.width, out.height);
      return out;
    }
  }

  // Lazily-created shared Tesseract worker.
  let workerPromise = null;
  async function getWorker(onStatus) {
    if (!workerPromise) {
      if (onStatus) onStatus("Loading recognizer…");
      workerPromise = Tesseract.createWorker("eng");
    }
    return workerPromise;
  }

  const LETTERS =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

  // Recognize handwriting. When `expected` is provided we know roughly what the
  // writing should be, so we tune page segmentation to a single word (or line)
  // and drop punctuation noise from the output.
  async function recognizeHandwriting(image, { expected, onStatus } = {}) {
    const w = await getWorker(onStatus);
    if (onStatus) onStatus("Reading your writing…");
    const multiWord = expected ? /\s/.test(String(expected).trim()) : true;
    await w.setParameters({
      // 8 = treat the image as a single word; 7 = a single text line.
      tessedit_pageseg_mode: multiWord ? "7" : "8",
      tessedit_char_whitelist: LETTERS + (multiWord ? " " : ""),
    });
    const { data } = await w.recognize(image);
    return {
      text: (data.text || "").replace(/\s+/g, " ").trim(),
      confidence: Math.round(data.confidence || 0),
    };
  }

  function normalizeAnswer(text, mode = "lenient") {
    let t = String(text).replace(/\s+/g, " ").trim();
    if (mode === "exact") return t;
    t = t.toLowerCase();
    if (mode === "normalized") return t;
    return t.replace(/[^a-z0-9]/g, ""); // lenient
  }

  // Standard Levenshtein edit distance.
  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      const curr = [i];
      for (let j = 1; j <= b.length; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
      }
      prev = curr;
    }
    return prev[b.length];
  }

  // Grade recognized text against the expected answer, biased heavily toward
  // "correct": since we already know the answer, an OCR near-miss (e.g. "doa"
  // for "dog") still counts. Only a clearly-different answer fails.
  //
  // We allow an edit-distance tolerance that scales with the answer length,
  // plus containment (recognized contains, or is contained in, expected).
  // Returns details so the UI can explain the decision.
  function gradeAnswer(recognized, expected, mode = "lenient") {
    const r = normalizeAnswer(recognized, mode);
    const e = normalizeAnswer(expected, mode);
    if (!e) return { correct: false, distance: 0, tolerance: 0, exactWrong: true };
    if (!r) return { correct: false, distance: e.length, tolerance: 0, exactWrong: true };

    const distance = levenshtein(r, e);
    // ~40% of the answer may differ and still pass (minimum of 1 edit).
    const tolerance = Math.max(1, Math.round(e.length * 0.4));
    const contained = e.includes(r) || r.includes(e);
    // Fuzzy, answer-biased leniency only applies in "lenient" mode; the
    // stricter modes require an exact match after normalization.
    const correct =
      r === e || (mode === "lenient" && (distance <= tolerance || contained));
    return { correct, distance, tolerance, similarity: 1 - distance / Math.max(r.length, e.length) };
  }

  // Kept for back-compat with the standalone checker.
  function answersMatch(recognized, expected, mode = "lenient") {
    return gradeAnswer(recognized, expected, mode).correct;
  }

  window.HandwritingPad = HandwritingPad;
  window.recognizeHandwriting = recognizeHandwriting;
  window.normalizeAnswer = normalizeAnswer;
  window.levenshtein = levenshtein;
  window.gradeAnswer = gradeAnswer;
  window.answersMatch = answersMatch;
})();
