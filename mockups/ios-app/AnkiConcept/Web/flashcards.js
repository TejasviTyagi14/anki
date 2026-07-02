// MCAT handwriting flashcard reviewer.
//
// A question (prompt) is shown; the learner supplies the short answer either by
// HANDWRITING it (Apple Pencil / finger / mouse, read with OCR) or by TYPING it
// via the fallback tab. The answer is graded against the expected solution.

const DECK = [
  // Biochemistry
  { subject: "Biochemistry",      prompt: "Which enzyme unwinds the DNA double helix at the replication fork?", answer: "Helicase" },
  { subject: "Biochemistry",      prompt: "What is the net charge of an amino acid at its isoelectric point (pI)?", answer: "Zero" },
  { subject: "Biochemistry",      prompt: "The Michaelis constant (K_m) equals the substrate concentration at what fraction of Vmax?", answer: "Half" },
  { subject: "Biochemistry",      prompt: "Which organelle is the primary site of ATP synthesis?", answer: "Mitochondria" },
  // General Chemistry
  { subject: "General Chemistry", prompt: "What is the pH of a 0.001 M HCl solution?", answer: "3" },
  { subject: "General Chemistry", prompt: "How many electrons completely fill a d subshell?", answer: "10" },
  { subject: "General Chemistry", prompt: "What kind of bond holds two water molecules together?", answer: "Hydrogen" },
  // Organic Chemistry
  { subject: "Organic Chemistry", prompt: "Non-superimposable mirror-image stereoisomers are called ___?", answer: "Enantiomers" },
  { subject: "Organic Chemistry", prompt: "Stereoisomers that differ at some but not all chiral centers are ___?", answer: "Diastereomers" },
  { subject: "Organic Chemistry", prompt: "A strong IR absorption near 1700 cm⁻¹ indicates which functional group?", answer: "Carbonyl" },
  // Physics
  { subject: "Physics",           prompt: "What is the SI unit of electric charge?", answer: "Coulomb" },
  { subject: "Physics",           prompt: "What is the SI unit of force?", answer: "Newton" },
  { subject: "Physics",           prompt: "What is the SI unit of frequency?", answer: "Hertz" },
  // Biology
  { subject: "Biology",           prompt: "What is the site of protein synthesis in the cell?", answer: "Ribosome" },
  { subject: "Biology",           prompt: "Which nephron structure filters blood in the kidney?", answer: "Glomerulus" },
  // Psych / Soc
  { subject: "Psych / Soc",       prompt: "Which hypothalamic nucleus is the body's master circadian pacemaker?", answer: "SCN" },
  { subject: "Psych / Soc",       prompt: "Which brain lobe is primarily responsible for processing vision?", answer: "Occipital" },
  { subject: "Psych / Soc",       prompt: "Which neurotransmitter is central to the brain's reward pathway?", answer: "Dopamine" },
];

const els = {
  count: document.getElementById("count"),
  progress: document.getElementById("progress"),
  subject: document.getElementById("subject"),
  cardSubject: document.getElementById("card-subject"),
  prompt: document.getElementById("prompt"),
  ask: document.getElementById("ask"),
  answerReveal: document.getElementById("answer-reveal"),
  verdict: document.getElementById("verdict"),
  check: document.getElementById("check"),
  next: document.getElementById("next"),
  status: document.getElementById("status"),
  undo: document.getElementById("undo"),
  clear: document.getElementById("clear"),
  importInput: document.getElementById("import"),
  canvasWrap: document.getElementById("canvas-wrap"),
  padBlock: document.getElementById("pad-block"),
  typeBlock: document.getElementById("type-block"),
  typeInput: document.getElementById("type-input"),
  modeWrite: document.getElementById("mode-write"),
  modeType: document.getElementById("mode-type"),
  summary: document.getElementById("summary"),
  summaryScore: document.getElementById("summary-score"),
  summarySub: document.getElementById("summary-sub"),
  restart: document.getElementById("restart"),
  // Desktop widgets
  wSeen: document.getElementById("w-seen"),
  wCorrect: document.getElementById("w-correct"),
  wAcc: document.getElementById("w-acc"),
  wStreak: document.getElementById("w-streak"),
  wBar: document.getElementById("w-bar"),
  wSubjects: document.getElementById("w-subjects"),
  wReads: document.getElementById("w-reads"),
};

const canvas = document.getElementById("pad");
const pad = new HandwritingPad(canvas, {
  onFirstInk: () => els.canvasWrap.classList.add("has-ink"),
});

let index = 0;
let score = 0;
let seen = 0;
let streak = 0;
let bestStreak = 0;
let answered = false;
let mode = "write"; // "write" | "type"

function card() { return DECK[index]; }

function renderCard() {
  const c = card();
  answered = false;

  els.count.textContent = `${index + 1} / ${DECK.length}`;
  els.progress.style.width = `${(index / DECK.length) * 100}%`;
  els.subject.textContent = c.subject;
  els.cardSubject.textContent = c.subject;
  els.prompt.textContent = c.prompt;
  els.ask.textContent = mode === "type" ? "Type your answer" : "Write your answer";

  els.answerReveal.hidden = true;
  els.answerReveal.className = "fcard-answer";
  els.verdict.hidden = true;
  els.verdict.className = "verdict";
  els.next.hidden = true;
  els.check.hidden = false;
  els.check.disabled = false;
  els.status.textContent = "";

  pad.clear();
  els.canvasWrap.classList.remove("has-ink");
  els.typeInput.value = "";

  renderSubjects();
  updateWidgets();
}

function setMode(next) {
  mode = next;
  const writing = mode === "write";
  els.modeWrite.classList.toggle("is-active", writing);
  els.modeType.classList.toggle("is-active", !writing);
  els.padBlock.hidden = !writing;
  els.typeBlock.hidden = writing;
  els.ask.textContent = writing ? "Write your answer" : "Type your answer";
  if (!writing) setTimeout(() => els.typeInput.focus(), 50);
}

async function checkAnswer() {
  const expected = card().answer;
  let text = "";

  if (mode === "type") {
    text = els.typeInput.value.trim();
    if (!text) { els.status.textContent = "Type your answer first."; return; }
  } else {
    if (!pad.hasInk) { els.status.textContent = "Write the answer first."; return; }
    els.check.disabled = true;
    try {
      const res = await recognizeHandwriting(pad.renderForOcr(), {
        expected,
        onStatus: (s) => (els.status.textContent = s),
      });
      text = res.text;
    } catch (err) {
      console.error(err);
      els.status.textContent = "Couldn't read the writing — try the Type tab.";
      els.check.disabled = false;
      return;
    }
  }

  const grade = gradeAnswer(text, expected, "lenient");
  const correct = grade.correct;

  seen++;
  if (correct) { score++; streak++; bestStreak = Math.max(bestStreak, streak); }
  else { streak = 0; }
  answered = true;

  els.status.textContent = "";
  els.verdict.hidden = false;
  els.verdict.classList.add(correct ? "correct" : "incorrect");
  const readAs = text || "nothing";
  const source = mode === "type" ? "Typed" : "Read";
  els.verdict.textContent = correct
    ? `✓ Correct — ${source.toLowerCase()} “${readAs}”${grade.distance ? " (close enough)" : ""}`
    : `✗ ${source} “${readAs}” — not a match`;

  els.answerReveal.hidden = false;
  els.answerReveal.classList.add(correct ? "correct" : "incorrect");
  els.answerReveal.textContent = card().answer;

  els.check.hidden = true;
  els.next.hidden = false;
  els.next.textContent = index + 1 < DECK.length ? "Next card →" : "See results →";

  if (els.wReads) els.wReads.textContent = readAs;
  updateWidgets();
}

function nextCard() {
  if (index + 1 < DECK.length) {
    index++;
    renderCard();
  } else {
    showSummary();
  }
}

function showSummary() {
  els.progress.style.width = "100%";
  document.querySelector(".rev").hidden = true;
  els.summary.hidden = false;
  els.summaryScore.textContent = `${score} / ${DECK.length}`;
  const pct = Math.round((score / DECK.length) * 100);
  els.summarySub.textContent =
    pct === 100 ? "Perfect — every answer correct!" : `${pct}% correct · best streak ${bestStreak}`;
}

function restart() {
  index = 0;
  score = 0;
  seen = 0;
  streak = 0;
  bestStreak = 0;
  els.summary.hidden = true;
  document.querySelector(".rev").hidden = false;
  renderCard();
}

// ---- Desktop widgets ----

function updateWidgets() {
  if (!els.wSeen) return;
  els.wSeen.textContent = `${seen} / ${DECK.length}`;
  els.wCorrect.textContent = `${score}`;
  els.wStreak.textContent = `${streak}`;
  const acc = seen ? Math.round((score / seen) * 100) : null;
  els.wAcc.textContent = acc === null ? "—" : `${acc}%`;
  if (els.wBar) els.wBar.style.width = acc === null ? "0%" : `${acc}%`;
}

function renderSubjects() {
  if (!els.wSubjects) return;
  const counts = {};
  for (const c of DECK) counts[c.subject] = (counts[c.subject] || 0) + 1;
  const current = card().subject;
  els.wSubjects.innerHTML = "";
  for (const [name, n] of Object.entries(counts)) {
    const li = document.createElement("li");
    li.className = "subject-item" + (name === current ? " is-current" : "");
    li.innerHTML = `<span class="subject-name">${name}</span><span class="subject-due">${n}</span>`;
    els.wSubjects.appendChild(li);
  }
}

// Controls
els.check.addEventListener("click", checkAnswer);
els.next.addEventListener("click", nextCard);
els.undo.addEventListener("click", () => {
  pad.undo();
  if (!pad.hasInk) els.canvasWrap.classList.remove("has-ink");
});
els.clear.addEventListener("click", () => {
  pad.clear();
  els.canvasWrap.classList.remove("has-ink");
});
els.restart.addEventListener("click", restart);
els.importInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) await pad.loadImageFile(file);
  els.importInput.value = "";
});
els.modeWrite.addEventListener("click", () => setMode("write"));
els.modeType.addEventListener("click", () => setMode("type"));
els.typeInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !answered) checkAnswer();
});

setMode("write");
renderCard();
