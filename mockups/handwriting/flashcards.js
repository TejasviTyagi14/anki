// Handwriting flashcard reviewer.
//
// Each card has two sides (here: Spanish + English). The SHORTER word is
// blanked out — the longer side is shown as the prompt — and the learner
// writes the missing (shorter) word by hand. The writing is read with OCR and
// compared to the hidden word to grade the card.

const DECK = [
  { es: "Perro", en: "Dog" },
  { es: "Gato", en: "Cat" },
  { es: "Casa", en: "House" },
  { es: "Manzana", en: "Apple" },
  { es: "Libro", en: "Book" },
  { es: "Agua", en: "Water" },
];

const LANG = { es: "Spanish", en: "English" };

// Build a review item: blank the shorter side, prompt with the longer side.
function toReviewItem(card) {
  const shorterKey = card.es.length <= card.en.length ? "es" : "en";
  const promptKey = shorterKey === "es" ? "en" : "es";
  return {
    promptWord: card[promptKey],
    promptLang: LANG[promptKey],
    answerWord: card[shorterKey],
    answerLang: LANG[shorterKey],
  };
}

const els = {
  count: document.getElementById("count"),
  progress: document.getElementById("progress"),
  promptLang: document.getElementById("prompt-lang"),
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
  rev: document.querySelector(".rev"),
  summary: document.getElementById("summary"),
  summaryScore: document.getElementById("summary-score"),
  summarySub: document.getElementById("summary-sub"),
  restart: document.getElementById("restart"),
};

const canvas = document.getElementById("pad");
const pad = new HandwritingPad(canvas, {
  onFirstInk: () => els.canvasWrap.classList.add("has-ink"),
});

let index = 0;
let score = 0;
let current = null;
let answered = false;

function renderCard() {
  current = toReviewItem(DECK[index]);
  answered = false;

  els.count.textContent = `${index + 1} / ${DECK.length}`;
  els.progress.style.width = `${(index / DECK.length) * 100}%`;
  els.promptLang.textContent = current.promptLang;
  els.prompt.textContent = current.promptWord;
  els.ask.textContent = `Write the ${current.answerLang} word`;

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
}

async function checkAnswer() {
  if (!pad.hasInk) {
    els.status.textContent = "Write the word first.";
    return;
  }
  els.check.disabled = true;
  try {
    const { text, confidence } = await recognizeHandwriting(pad.renderForOcr(), {
      expected: current.answerWord,
      onStatus: (s) => (els.status.textContent = s),
    });
    const grade = gradeAnswer(text, current.answerWord, "lenient");
    const correct = grade.correct;
    if (correct) score++;
    answered = true;

    els.status.textContent = "";
    els.verdict.hidden = false;
    els.verdict.classList.add(correct ? "correct" : "incorrect");
    const readAs = text || "nothing";
    els.verdict.textContent = correct
      ? `✓ Correct — read “${readAs}”${grade.distance ? ` (close enough)` : ""}`
      : `✗ Read “${readAs}” — too different`;

    els.answerReveal.hidden = false;
    els.answerReveal.classList.add(correct ? "correct" : "incorrect");
    els.answerReveal.textContent = current.answerWord;

    els.check.hidden = true;
    els.next.hidden = false;
    els.next.textContent =
      index + 1 < DECK.length ? "Next card →" : "See results →";
  } catch (err) {
    console.error(err);
    els.status.textContent = "Couldn't read the writing — try again.";
    els.check.disabled = false;
  }
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
  els.rev.hidden = true;
  els.summary.hidden = false;
  els.summaryScore.textContent = `${score} / ${DECK.length}`;
  const pct = Math.round((score / DECK.length) * 100);
  els.summarySub.textContent =
    pct === 100 ? "Perfect — every word read correctly!" : `${pct}% correct`;
}

function restart() {
  index = 0;
  score = 0;
  els.summary.hidden = true;
  els.rev.hidden = false;
  renderCard();
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
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-active"));
    chip.classList.add("is-active");
    pad.setPenSize(chip.dataset.size);
  });
});

renderCard();
