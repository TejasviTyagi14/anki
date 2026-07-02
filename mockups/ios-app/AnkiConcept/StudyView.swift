import SwiftUI
import PencilKit

enum AnswerMode: String, CaseIterable, Identifiable {
    case handwrite = "Handwrite"
    case type = "Type"
    var id: String { rawValue }
}

struct StudyView: View {
    let deck: Deck

    @State private var index = 0
    @State private var mode: AnswerMode = .handwrite
    @State private var drawing = PKDrawing()
    @State private var typed = ""
    @State private var recognized = ""
    @State private var isEraser = false
    @State private var isRecognizing = false
    @State private var revealed = false

    private var cards: [FlashCard] { MCAT.cards(for: deck.name) }
    private var card: FlashCard { cards[index % cards.count] }
    private var userAnswer: String { mode == .handwrite ? recognized : typed }

    private var isCorrect: Bool {
        let norm = normalizeAnswer(userAnswer)
        guard norm.count >= 1 else { return false }
        return card.accepted.contains { acc in
            let a = normalizeAnswer(acc)
            return norm == a || norm.contains(a) || a.contains(norm)
        }
    }

    var body: some View {
        VStack(spacing: 18) {
            questionCard
            answerPanel
            Spacer(minLength: 0)
            controls
        }
        .padding(24)
        .frame(maxWidth: 820)
        .frame(maxWidth: .infinity)
        .background(Color(.systemGroupedBackground))
        .navigationTitle(deck.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                DeckCounts(deck: deck)
            }
        }
    }

    // MARK: Question

    private var questionCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(deck.name, systemImage: deck.systemImage)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(deck.tint)
            Text(card.prompt)
                .font(.system(size: 26, weight: .bold))
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(22)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
    }

    // MARK: Answer input (Handwrite / Type tabs)

    private var answerPanel: some View {
        VStack(spacing: 12) {
            Picker("Answer mode", selection: $mode) {
                ForEach(AnswerMode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)

            if mode == .handwrite {
                handwriteArea
            } else {
                typeArea
            }
        }
        .padding(18)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
    }

    private var handwriteArea: some View {
        VStack(spacing: 10) {
            ZStack(alignment: .bottomLeading) {
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color(.systemBackground))
                    .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color(.separator)))
                HandwritingCanvas(drawing: $drawing, isEraser: isEraser)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                if drawing.strokes.isEmpty {
                    Text("Write your answer with the Apple Pencil")
                        .font(.system(size: 15))
                        .foregroundStyle(.tertiary)
                        .padding(18)
                        .allowsHitTesting(false)
                }
            }
            .frame(height: 240)

            HStack(spacing: 10) {
                Button { isEraser = false } label: {
                    Label("Pen", systemImage: "pencil.tip")
                }
                .buttonStyle(.bordered)
                .tint(isEraser ? .secondary : .ankiBlue)

                Button { isEraser = true } label: {
                    Label("Eraser", systemImage: "eraser")
                }
                .buttonStyle(.bordered)
                .tint(isEraser ? .ankiBlue : .secondary)

                Button(role: .destructive) {
                    drawing = PKDrawing(); recognized = ""
                } label: {
                    Label("Clear", systemImage: "trash")
                }
                .buttonStyle(.bordered)

                Spacer()

                if isRecognizing {
                    ProgressView()
                } else if !recognized.isEmpty {
                    Text("Reads: \(recognized)")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
    }

    private var typeArea: some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("Type your answer", text: $typed)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 20))
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .onSubmit { reveal() }
            Text("Fallback for when handwriting doesn't recognize cleanly.")
                .font(.footnote)
                .foregroundStyle(.tertiary)
        }
        .frame(height: 240, alignment: .top)
        .padding(.top, 4)
    }

    // MARK: Reveal + rating

    @ViewBuilder
    private var controls: some View {
        if revealed {
            VStack(spacing: 14) {
                answerReveal
                HStack(spacing: 10) {
                    rating("Again", "<1m", .ankiLearn)
                    rating("Hard", "8m", .ankiHard)
                    rating("Good", "1d", .ankiDue)
                    rating("Easy", "4d", .ankiEasy)
                }
            }
        } else {
            Button(action: reveal) {
                Text(isRecognizing ? "Reading…" : "Show Answer")
                    .font(.system(size: 18, weight: .bold))
                    .frame(maxWidth: .infinity, minHeight: 54)
            }
            .buttonStyle(.borderedProminent)
            .tint(.ankiBlue)
            .disabled(isRecognizing)
        }
    }

    private var answerReveal: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: isCorrect ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(isCorrect ? Color.ankiDue : Color.ankiLearn)
                Text(isCorrect ? "Matched your answer" : "Your answer: \(userAnswer.isEmpty ? "—" : userAnswer)")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
            Text(card.answer)
                .font(.system(size: 24, weight: .bold))
            Text(card.explanation)
                .font(.system(size: 15))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private func rating(_ label: String, _ interval: String, _ color: Color) -> some View {
        Button(action: next) {
            VStack(spacing: 2) {
                Text(label).font(.system(size: 16, weight: .bold))
                Text(interval).font(.system(size: 12, weight: .semibold)).opacity(0.9)
            }
            .frame(maxWidth: .infinity, minHeight: 52)
            .foregroundStyle(.white)
            .background(color, in: RoundedRectangle(cornerRadius: 13))
        }
    }

    // MARK: Actions

    private func reveal() {
        if mode == .handwrite {
            isRecognizing = true
            Task {
                recognized = await Handwriting.recognize(drawing)
                isRecognizing = false
                withAnimation(.easeOut(duration: 0.15)) { revealed = true }
            }
        } else {
            withAnimation(.easeOut(duration: 0.15)) { revealed = true }
        }
    }

    private func next() {
        withAnimation(.easeInOut(duration: 0.15)) {
            index += 1
            revealed = false
            drawing = PKDrawing()
            typed = ""
            recognized = ""
            isEraser = false
        }
    }
}

#Preview {
    NavigationStack { StudyView(deck: MCAT.subjects[0]) }
}
