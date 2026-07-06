/*
 * flashcards.js — UI controller: fetch cards, wire the toolbar, autosave the
 * drawing per card, grade on demand, and render feedback.
 *
 * Depends on window.MoleculeEditor, window.Grader.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const LS = {
    drawing: (id) => `ochem_flash_${id}`,
    ink: (id) => `ochem_ink_${id}`,
    customText: "ochem_flash_custom_text",
  };
  const EMPTY = { atoms: [], bonds: [], arrows: [], texts: [] };

  const CUSTOM = { id: "custom", title: "✍️ Custom question (type your own)", mechanism: "Your question", statement: "" };
  const VLABEL = { correct: "Correct", partially_correct: "Partially correct", incorrect: "Incorrect" };
  const VICON = { correct: "✓", partially_correct: "≈", incorrect: "✗" };

  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const editor = new window.MoleculeEditor($("canvas"), onEditorChange);
  const freehand = new window.FreehandCanvas($("inkCanvas"), onInkChange);
  let problems = [CUSTOM];
  let current = CUSTOM;
  let mode = "structured"; // "structured" | "freehand"
  let customElement = null; // last custom element symbol chosen
  let saveTimer = null;
  let grading = false;

  // ---------- autosave (persists both surfaces per card) ----------
  function saveNow() {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    if (!current) return;
    localStorage.setItem(LS.drawing(current.id), JSON.stringify(editor.getMol()));
    localStorage.setItem(LS.ink(current.id), JSON.stringify(freehand.getStrokes()));
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 400);
  }
  function onEditorChange() {
    updateReadouts();
    scheduleSave();
  }
  function onInkChange() {
    scheduleSave();
  }
  window.addEventListener("beforeunload", saveNow);

  function setMode(m) {
    mode = m;
    document.body.dataset.mode = m;
    document.querySelectorAll(".mode-btn").forEach((b) => {
      const on = b.dataset.mode === m;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  function updateReadouts() {
    const payload = window.Grader.buildSubmission(editor.getMol());
    $("smilesReadout").textContent = window.Grader.smilesReadout(payload);
    $("payloadPre").textContent = JSON.stringify(payload, null, 2);
  }

  // ---------- problem display ----------
  function populateSelect() {
    const sel = $("problemSelect");
    sel.innerHTML = "";
    for (const p of problems) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.title;
      sel.appendChild(opt);
    }
  }

  function showProblem(id) {
    const p = problems.find((x) => x.id === id) || CUSTOM;
    current = p;
    $("problemSelect").value = p.id;
    $("problemTag").textContent = p.mechanism || "";
    $("feedback").innerHTML = "";

    const isCustom = p.id === "custom";
    $("customProblem").hidden = !isCustom;
    $("problemStatement").hidden = isCustom;
    if (isCustom) {
      $("customProblem").value = localStorage.getItem(LS.customText) || "";
    } else {
      $("problemStatement").textContent = p.statement || "";
    }

    const raw = localStorage.getItem(LS.drawing(p.id));
    let mol = EMPTY;
    if (raw) {
      try {
        mol = JSON.parse(raw);
      } catch (_) {}
    }
    editor.loadMol(mol); // triggers onEditorChange -> readouts + save

    const rawInk = localStorage.getItem(LS.ink(p.id));
    let strokes = [];
    if (rawInk) {
      try {
        strokes = JSON.parse(rawInk);
      } catch (_) {}
    }
    freehand.loadStrokes(strokes);
  }

  function nextCard() {
    const real = problems.filter((p) => p.id !== "custom");
    if (!real.length) return;
    const i = real.findIndex((p) => p.id === current.id);
    const next = real[(i + 1 + real.length) % real.length] || real[0];
    saveNow();
    showProblem(next.id);
  }

  // ---------- toolbar ----------
  function setTool(tool) {
    editor.tool = tool;
    document.querySelectorAll(".tool-btn[data-tool]").forEach((b) => {
      const on = b.dataset.tool === tool;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }

  function setElement(el) {
    editor.element = el;
    document.querySelectorAll(".el-btn").forEach((b) => {
      const on = b.dataset.el === el || (b.dataset.el === "__custom__" && el === customElement);
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
    // picking an element implies you want to draw
    if (!["draw", "wedge", "hash"].includes(editor.tool)) setTool("draw");
  }

  function wireToolbar() {
    document.querySelectorAll(".tool-btn[data-tool]").forEach((b) => {
      b.addEventListener("click", () => setTool(b.dataset.tool));
    });
    document.querySelectorAll(".el-btn").forEach((b) => {
      b.addEventListener("click", () => {
        if (b.dataset.el === "__custom__") {
          const s = (prompt("Element symbol (e.g. Zn, Li, Mg):", customElement || "") || "").trim();
          if (!s) return;
          if (!/^[A-Z][a-z]?$/.test(s)) {
            alert("Use an element symbol like C, Br, or Zn (one capital, optional lowercase).");
            return;
          }
          customElement = s;
          b.textContent = s;
          setElement(s);
        } else {
          setElement(b.dataset.el);
        }
      });
    });
    $("undoBtn").addEventListener("click", () => editor.undo());
    $("clearBtn").addEventListener("click", () => editor.clear());
    $("problemSelect").addEventListener("change", (e) => {
      saveNow();
      showProblem(e.target.value);
    });
    $("nextCard").addEventListener("click", nextCard);
    $("customProblem").addEventListener("input", (e) => {
      localStorage.setItem(LS.customText, e.target.value);
    });
    $("gradeBtn").addEventListener("click", onGrade);

    // mode toggle
    document.querySelectorAll(".mode-btn").forEach((b) => {
      b.addEventListener("click", () => setMode(b.dataset.mode));
    });

    // freehand tools
    document.querySelectorAll("[data-ftool]").forEach((b) => {
      b.addEventListener("click", () => {
        freehand.setTool(b.dataset.ftool);
        document.querySelectorAll("[data-ftool]").forEach((x) => {
          const on = x === b;
          x.classList.toggle("active", on);
          x.setAttribute("aria-pressed", String(on));
        });
      });
    });
    document.querySelectorAll("[data-fsize]").forEach((b) => {
      b.addEventListener("click", () => {
        freehand.setWidth(parseFloat(b.dataset.fsize));
        document.querySelectorAll("[data-fsize]").forEach((x) => x.classList.toggle("active", x === b));
      });
    });
    $("fUndo").addEventListener("click", () => freehand.undo());
    $("fClear").addEventListener("click", () => freehand.clear());

    // Ctrl/Cmd+Z undoes the ink in freehand mode (before the editor's handler)
    document.addEventListener(
      "keydown",
      (e) => {
        if (mode === "freehand" && (e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
          e.preventDefault();
          e.stopImmediatePropagation();
          freehand.undo();
        }
      },
      true
    );

    setTool("draw");
    setElement("C");
    setMode("structured");
    document.querySelector('[data-ftool="pen"]').classList.add("active");
    document.querySelector('[data-fsize="3.2"]').classList.add("active");
  }

  // ---------- grading ----------
  async function onGrade() {
    if (grading) return;
    const isCustom = current.id === "custom";
    const statement = isCustom ? $("customProblem").value.trim() : current.statement;
    if (isCustom && !statement) {
      showError("Type your question first, then draw the answer.");
      return;
    }
    if (mode === "freehand") {
      if (freehand.isEmpty()) {
        showError("Sketch your answer first.");
        return;
      }
    } else if (!editor.getMol().atoms.length) {
      showError("Draw your answer on the canvas first.");
      return;
    }

    grading = true;
    const btn = $("gradeBtn");
    btn.disabled = true;
    btn.classList.add("busy");
    $("feedback").innerHTML = "";
    try {
      const hint = $("hintMode").checked;
      const result =
        mode === "freehand"
          ? await window.Grader.gradeFreehand({
              problemId: current.id,
              statement,
              imageBase64: freehand.toPngBase64(),
              hint,
            })
          : await window.Grader.gradeSubmission({
              problemId: current.id,
              statement,
              mol: editor.getMol(),
              svg: editor.svg,
              hint,
            });
      renderFeedback(result);
    } catch (e) {
      showError(e && e.message ? e.message : "Grading failed.");
    } finally {
      grading = false;
      btn.disabled = false;
      btn.classList.remove("busy");
    }
  }

  function showError(msg) {
    $("feedback").innerHTML = `<div class="card"><div class="error-box">${esc(msg)}</div></div>`;
  }

  function listSection(title, items, cls) {
    if (!items || !items.length) return "";
    return (
      `<div class="fb-section"><h3>${esc(title)}</h3><ul class="fb-list ${cls}">` +
      items.map((i) => `<li>${esc(i)}</li>`).join("") +
      `</ul></div>`
    );
  }

  function structureCheckHtml(sc) {
    if (!sc || !sc.note) return "";
    let cls = "",
      icon = "•";
    if (sc.connectivity_match === true) {
      cls = "match";
      icon = "✓";
    } else if (sc.connectivity_match === false) {
      cls = "nomatch";
      icon = "✗";
    }
    return `<div class="structure-check ${cls}">${icon} ${esc(sc.note)}</div>`;
  }

  function modelAnswerHtml(ma, hint) {
    if (!ma) return "";
    const hasSolution = (ma.name && ma.name.trim()) || (ma.smiles && ma.smiles.trim());
    if (!hasSolution && !(ma.reasoning && ma.reasoning.trim())) return "";
    const title = hint ? "Hint" : "How I'd solve it";
    let inner = "";
    if (hasSolution) {
      inner += `<div class="ma-name">${esc(ma.name || "")}</div>`;
      if (ma.smiles && ma.smiles.trim()) inner += `<div class="ma-smiles">${esc(ma.smiles)}</div>`;
    }
    if (ma.reasoning && ma.reasoning.trim()) inner += `<p class="ma-reason">${esc(ma.reasoning)}</p>`;
    return `<div class="model-answer"><h3>${esc(title)}</h3>${inner}</div>`;
  }

  function renderFeedback(r) {
    const verdict = r.verdict || "partially_correct";
    const hint = $("hintMode").checked;
    const html =
      `<div class="card">` +
      `<div class="verdict-row">` +
      `<span class="verdict-badge verdict-${esc(verdict)}">${VICON[verdict] || ""} ${esc(VLABEL[verdict] || verdict)}</span>` +
      `<span class="score">${esc(r.score)}<small>/10</small></span>` +
      `</div>` +
      (r.summary ? `<p class="fb-summary">${esc(r.summary)}</p>` : "") +
      structureCheckHtml(r.structure_check) +
      listSection("What you got right", r.what_is_right, "good") +
      listSection("What to fix", r.what_is_wrong, "bad") +
      (r.explanation ? `<div class="fb-section"><h3>Why</h3><p class="explanation">${esc(r.explanation)}</p></div>` : "") +
      modelAnswerHtml(r.model_answer, hint) +
      (r.study_tip ? `<div class="study-tip"><b>📚 Study tip.</b> ${esc(r.study_tip)}</div>` : "") +
      `</div>`;
    $("feedback").innerHTML = html;
  }

  // ---------- init ----------
  async function init() {
    wireToolbar();
    let real = [];
    try {
      const res = await fetch("/flashcards");
      if (res.ok) real = await res.json();
    } catch (_) {}
    problems = [CUSTOM, ...real];
    populateSelect();
    const start = real.length ? real[0].id : "custom";
    showProblem(start);
  }

  init();
})();
