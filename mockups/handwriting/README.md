# Handwriting Answer Checker

A small, self-contained web app that takes **handwritten input**, converts it
to text, and checks whether it matches an expected answer. Built as a side
prototype for a handwriting-based flashcard review flow.

Two pages:

- **`index.html`** — the standalone checker (set any question/solution, write, check).
- **`flashcards.html`** — a flashcard reviewer that integrates handwriting into
  a study flow (see below).

## Flashcard reviewer (`flashcards.html`)

A working review flow for a Spanish/English vocabulary deck. For each card the
**shorter of the two words is blanked out**, the longer side is shown as the
prompt, and you **write the missing word by hand**. The writing is read with
OCR and compared to the hidden word to grade the card. It tracks a score and
shows a summary at the end.

The recognizer + drawing pad are shared with the standalone checker via
`pad.js` (`HandwritingPad`, `recognizeHandwriting`, `answersMatch`).

## What it does

1. **Capture writing** from any pointer device:
   - Mouse or trackpad on a laptop/desktop
   - Finger or Apple Pencil on an iPad / iPhone (open the page in Safari)
2. **Or import a drawing** — take a photo or export an iPad/iPhone sketch and
   load it with the *Import image* button.
3. **Recognize** the writing as natural-language text using
   [Tesseract.js](https://github.com/naptha/tesseract.js) (runs entirely in the
   browser — no API keys, no server).
4. **Check** the recognized text against the expected solution and show a
   correct / not-a-match verdict, the text it read, and a confidence score.

## Running it

It's just static files. Because Tesseract.js loads a WebAssembly worker, serve
it over HTTP rather than opening the file directly:

```bash
cd mockups/handwriting
python3 -m http.server 8000
```

Then open http://localhost:8000 for the standalone checker, or
http://localhost:8000/flashcards.html for the reviewer — or, to write on an
iPad/iPhone, open `http://<your-computer-ip>:8000` on the device while on the
same network.

## Recognition & grading

Recognition is tuned for short answers: the pad image is upscaled before OCR,
single-word page segmentation is used, and output is restricted to
letters/digits to drop punctuation noise.

Grading is **biased toward the known answer**. Because we already know what the
word should be, an OCR near-miss still counts — e.g. reading `doa` for `dog`,
or `watar` for `water`, is marked correct. It uses edit-distance tolerance
(~40% of the answer length, minimum one edit) plus containment, so only a
clearly-different answer (`cat` for `dog`, `banana` for `apple`) fails.

## Matching modes (standalone checker)

- **Lenient** — answer-biased fuzzy match described above (recommended)
- **Normalized** — exact match ignoring case and extra spaces
- **Exact** — must match character for character

## Notes & limitations

- Recognition quality depends on neatness. Print-style letters and digits work
  best; cursive is hit-or-miss. It's tuned for short, single-line answers.
- The first check downloads the English model (~a few MB) from a CDN, so the
  first run needs a network connection.
- Files: `index.html` + `app.js` (checker), `flashcards.html` + `flashcards.js`
  + `flashcards.css` (reviewer), shared `pad.js` and `styles.css` — no build step.
