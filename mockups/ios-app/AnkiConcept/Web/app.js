// Standalone handwriting answer checker.
// Uses the shared engine in pad.js (HandwritingPad + recognizeHandwriting +
// gradeAnswer) so it stays consistent with the flashcard reviewer.

const canvas = document.getElementById("pad");
const wrap = document.getElementById("canvas-wrap") || canvas.parentElement;

const els = {
  question: document.getElementById("question"),
  solution: document.getElementById("solution"),
  matchMode: document.getElementById("match-mode"),
  check: document.getElementById("check"),
  clear: document.getElementById("clear"),
  undo: document.getElementById("undo"),
  importInput: document.getElementById("import"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  verdict: document.getElementById("verdict"),
  recognized: document.getElementById("recognized"),
  expected: document.getElementById("expected"),
  confidence: document.getElementById("confidence"),
};

const pad = new HandwritingPad(canvas, {
  onFirstInk: () => wrap.classList.add("has-ink"),
});

els.clear.addEventListener("click", () => {
  pad.clear();
  wrap.classList.remove("has-ink");
  els.result.hidden = true;
  els.status.textContent = "";
});

els.undo.addEventListener("click", () => {
  pad.undo();
  if (!pad.hasInk) wrap.classList.remove("has-ink");
});

els.importInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) {
    await pad.loadImageFile(file);
    els.result.hidden = true;
  }
  els.importInput.value = "";
});

async function checkAnswer() {
  if (!pad.hasInk) {
    els.status.textContent = "Write an answer first.";
    return;
  }
  const solution = els.solution.value;
  if (!solution.trim()) {
    els.status.textContent = "Set an expected answer to check against.";
    return;
  }

  els.check.disabled = true;
  els.result.hidden = true;
  try {
    const mode = els.matchMode.value;
    const { text, confidence } = await recognizeHandwriting(pad.renderForOcr(), {
      expected: solution,
      onStatus: (s) => (els.status.textContent = s),
    });
    const grade = gradeAnswer(text, solution, mode);

    els.recognized.textContent = text || "(nothing recognized)";
    els.expected.textContent = solution;
    els.confidence.textContent =
      `${confidence}%` + (grade.correct && grade.distance ? " · close enough" : "");
    els.verdict.textContent = grade.correct ? "✓ Correct" : "✗ Not a match";
    els.verdict.className = "verdict " + (grade.correct ? "correct" : "incorrect");
    els.result.hidden = false;
    els.status.textContent = "";
  } catch (err) {
    console.error(err);
    els.status.textContent = "Something went wrong while reading. Check the console.";
  } finally {
    els.check.disabled = false;
  }
}

els.check.addEventListener("click", checkAnswer);
