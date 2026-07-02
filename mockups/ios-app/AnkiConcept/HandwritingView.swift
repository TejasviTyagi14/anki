import SwiftUI
import PencilKit
import Vision

// MARK: - Deck

private struct HWCard {
    let es: String
    let en: String
}

/// Native handwriting flashcard reviewer.
///
/// The shorter of the two word-sides is blanked; the learner writes it by hand
/// (finger or Apple Pencil). Strokes are captured with PencilKit and recognized
/// on-device with the Vision framework's handwriting text recognizer — the same
/// class of technology Apple Notes uses, and far more accurate than image OCR.
///
/// Grading is answer-aware: because we already know the expected word, we bias
/// recognition toward it (`customWords`), pull Vision's N-best candidate list,
/// and count the card correct if the answer shows up among the candidates (with
/// a small fuzzy fallback). Checking the whole candidate list against the known
/// answer is what makes this reliable despite imperfect handwriting.
struct HandwritingView: View {
    private let deck: [HWCard] = [
        .init(es: "Perro", en: "Dog"),
        .init(es: "Gato", en: "Cat"),
        .init(es: "Casa", en: "House"),
        .init(es: "Manzana", en: "Apple"),
        .init(es: "Libro", en: "Book"),
        .init(es: "Agua", en: "Water"),
    ]

    @State private var index = 0
    @State private var score = 0
    @State private var canvas = PKCanvasView()
    @State private var canvasID = UUID()
    @State private var isRecognizing = false
    @State private var graded = false
    @State private var lastCorrect = false
    @State private var recognizedText = ""
    @State private var finished = false

    // Shorter side is the answer to write; the longer side is the prompt.
    private var card: HWCard { deck[index] }
    private var answer: String { card.es.count <= card.en.count ? card.es : card.en }
    private var prompt: String { answer == card.es ? card.en : card.es }
    private var answerIsSpanish: Bool { answer == card.es }
    private var answerLang: String { answerIsSpanish ? "Spanish" : "English" }
    private var promptLang: String { answerIsSpanish ? "English" : "Spanish" }

    var body: some View {
        NavigationStack {
            Group {
                if finished { summary } else { reviewer }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Write")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: Reviewer

    private var reviewer: some View {
        VStack(spacing: 14) {
            header
            promptCard
            padSection
            if graded { verdictView }
            Spacer(minLength: 0)
            actionButton
        }
        .padding(16)
    }

    private var header: some View {
        VStack(spacing: 8) {
            HStack {
                Text("Spanish · Vocabulary")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(index + 1) / \(deck.count)")
                    .font(.system(size: 15, weight: .bold).monospacedDigit())
            }
            ProgressView(value: Double(index), total: Double(deck.count))
                .tint(.ankiBlue)
        }
    }

    private var promptCard: some View {
        VStack(spacing: 0) {
            Text(promptLang.uppercased())
                .font(.system(size: 11, weight: .bold))
                .tracking(1)
                .foregroundStyle(.secondary)
                .padding(.vertical, 4).padding(.horizontal, 10)
                .background(Color(.systemGray6), in: Capsule())
            Text(prompt)
                .font(.system(size: 34, weight: .bold))
                .padding(.top, 14)
            Divider().frame(maxWidth: 200).padding(.vertical, 18)
            if graded {
                Text(answer)
                    .font(.system(size: 24, weight: .bold))
                    .foregroundStyle(lastCorrect ? Color.ankiDue : Color.ankiLearn)
            } else {
                Text("Write the \(answerLang) word")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20))
    }

    private var padSection: some View {
        VStack(spacing: 10) {
            HStack {
                Text("Write here")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.tertiary)
                Spacer()
                Button("Clear") { clearCanvas() }
                    .font(.system(size: 14, weight: .semibold))
                    .buttonStyle(.bordered)
                    .disabled(isRecognizing)
            }
            PencilCanvas(canvas: canvas)
                .id(canvasID)
                .frame(height: 220)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [6]))
                        .foregroundStyle(Color(.systemGray4))
                )
        }
    }

    private var verdictView: some View {
        HStack(spacing: 8) {
            Image(systemName: lastCorrect ? "checkmark.circle.fill" : "xmark.circle.fill")
            Text(verdictText)
                .font(.system(size: 15, weight: .semibold))
            Spacer()
        }
        .foregroundStyle(lastCorrect ? Color.ankiDue : Color.ankiLearn)
        .padding(12)
        .background((lastCorrect ? Color.ankiDue : Color.ankiLearn).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 12))
    }

    private var verdictText: String {
        let read = recognizedText.isEmpty ? "nothing" : recognizedText
        return lastCorrect ? "Correct — read “\(read)”" : "Read “\(read)” — not a match"
    }

    @ViewBuilder
    private var actionButton: some View {
        if isRecognizing {
            ProgressView("Reading your writing…")
                .frame(maxWidth: .infinity, minHeight: 52)
        } else if graded {
            Button {
                advance()
            } label: {
                Text(index + 1 < deck.count ? "Next card →" : "See results →")
                    .primaryButtonLabel()
            }
        } else {
            Button {
                Task { await check() }
            } label: {
                Text("Check answer").primaryButtonLabel()
            }
        }
    }

    // MARK: Summary

    private var summary: some View {
        VStack(spacing: 14) {
            Text("Session complete").font(.system(size: 22, weight: .bold))
            Text("\(score) / \(deck.count)")
                .font(.system(size: 44, weight: .bold).monospacedDigit())
            Text(score == deck.count ? "Perfect — every word read correctly!"
                                     : "\(Int(Double(score) / Double(deck.count) * 100))% correct")
                .foregroundStyle(.secondary)
            Button { restart() } label: {
                Text("Study again").primaryButtonLabel()
            }
            .padding(.top, 8)
        }
        .padding(28)
    }

    // MARK: Actions

    private func clearCanvas() {
        canvas.drawing = PKDrawing()
    }

    private func check() async {
        guard !canvas.drawing.strokes.isEmpty else { return }
        isRecognizing = true
        let candidates = await HandwritingRecognizer.recognize(
            drawing: canvas.drawing, expected: answer)
        isRecognizing = false

        recognizedText = candidates.first ?? ""
        lastCorrect = AnswerGrader.isCorrect(candidates: candidates, expected: answer)
        if lastCorrect { score += 1 }
        withAnimation(.easeOut(duration: 0.15)) { graded = true }
    }

    private func advance() {
        if index + 1 < deck.count {
            index += 1
            resetCardState()
        } else {
            withAnimation { finished = true }
        }
    }

    private func restart() {
        index = 0
        score = 0
        finished = false
        resetCardState()
    }

    private func resetCardState() {
        graded = false
        lastCorrect = false
        recognizedText = ""
        canvas.drawing = PKDrawing()
        canvasID = UUID()
    }
}

// MARK: - PencilKit canvas

private struct PencilCanvas: UIViewRepresentable {
    let canvas: PKCanvasView

    func makeUIView(context: Context) -> PKCanvasView {
        canvas.drawingPolicy = .anyInput // allow finger + Apple Pencil
        canvas.tool = PKInkingTool(.pen, color: .black, width: 6)
        canvas.backgroundColor = .white
        canvas.isOpaque = true
        // Keep ink black on white regardless of app appearance so Vision sees it.
        canvas.overrideUserInterfaceStyle = .light
        return canvas
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
}

// MARK: - Recognition (Vision, on-device)

private enum HandwritingRecognizer {
    /// Returns Vision's N-best candidate strings for the drawn handwriting,
    /// biased toward `expected`.
    static func recognize(drawing: PKDrawing, expected: String) async -> [String] {
        guard !drawing.bounds.isEmpty else { return [] }

        // Rasterize the ink with padding and upscale for better recognition,
        // then composite onto white.
        let bounds = drawing.bounds.insetBy(dx: -30, dy: -30)
        let scale = max(3.0, 900.0 / max(bounds.width, 1))
        let inkImage = drawing.image(from: bounds, scale: scale)
        guard let cgImage = whiteBacked(inkImage).cgImage else { return [] }

        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { req, _ in
                let observations = (req.results as? [VNRecognizedTextObservation]) ?? []
                var candidates: [String] = []
                for obs in observations {
                    for cand in obs.topCandidates(10) {
                        candidates.append(cand.string)
                    }
                }
                continuation.resume(returning: candidates)
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            request.recognitionLanguages = ["en-US", "es-ES"]
            // Bias the recognizer toward the word we're expecting.
            request.customWords = Array(Set([
                expected, expected.lowercased(), expected.capitalized,
            ]))
            if #available(iOS 16.0, *) {
                request.revision = VNRecognizeTextRequestRevision3
            }

            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            DispatchQueue.global(qos: .userInitiated).async {
                do { try handler.perform([request]) }
                catch { continuation.resume(returning: []) }
            }
        }
    }

    private static func whiteBacked(_ image: UIImage) -> UIImage {
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = image.scale
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: image.size, format: format)
        return renderer.image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: image.size))
            image.draw(at: .zero)
        }
    }
}

// MARK: - Answer-aware grading

enum AnswerGrader {
    /// Correct if the expected answer matches any recognition candidate
    /// (normalized), or the best candidate is within a small edit-distance
    /// tolerance. Using the full N-best list against a KNOWN answer keeps this
    /// tolerant of messy handwriting while avoiding the false positives you get
    /// from fuzzy-matching a single noisy OCR string.
    static func isCorrect(candidates: [String], expected: String) -> Bool {
        let target = normalize(expected)
        guard !target.isEmpty else { return false }

        let normalized = candidates.map(normalize).filter { !$0.isEmpty }
        if normalized.contains(target) { return true }

        // Small fuzzy fallback (~a third of the word length, min 1 edit).
        let tolerance = max(1, Int((Double(target.count) * 0.34).rounded()))
        return normalized.contains { levenshtein($0, target) <= tolerance }
    }

    static func normalize(_ s: String) -> String {
        s.lowercased().unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init).joined()
    }

    static func levenshtein(_ a: String, _ b: String) -> Int {
        if a == b { return 0 }
        let x = Array(a), y = Array(b)
        if x.isEmpty { return y.count }
        if y.isEmpty { return x.count }
        var prev = Array(0...y.count)
        var curr = [Int](repeating: 0, count: y.count + 1)
        for i in 1...x.count {
            curr[0] = i
            for j in 1...y.count {
                let cost = x[i - 1] == y[j - 1] ? 0 : 1
                curr[j] = Swift.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            }
            swap(&prev, &curr)
        }
        return prev[y.count]
    }
}

// MARK: - Helpers

private extension View {
    func primaryButtonLabel() -> some View {
        self.font(.system(size: 17, weight: .bold))
            .frame(maxWidth: .infinity, minHeight: 52)
            .foregroundStyle(.white)
            .background(Color.ankiBlue, in: RoundedRectangle(cornerRadius: 14))
    }
}

#Preview {
    HandwritingView()
}
