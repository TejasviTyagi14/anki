import SwiftUI

/// iPad-first layout: a persistent subject sidebar + a large study detail pane.
/// Intentionally different from the desktop dashboard and the iPhone tab-bar idiom.
struct RootView: View {
    @State private var selection: UUID? = MCAT.subjects.first?.id

    var body: some View {
        NavigationSplitView {
            List(MCAT.subjects, selection: $selection) { deck in
                SubjectRow(deck: deck)
            }
            .navigationTitle("MCAT")
            .safeAreaInset(edge: .bottom) {
                Text("Studied 84 cards in 46 minutes today")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(.bar)
            }
        } detail: {
            if let id = selection, let deck = MCAT.subjects.first(where: { $0.id == id }) {
                StudyView(deck: deck)
                    .id(deck.id)
            } else {
                ContentUnavailableView("Select a subject",
                                       systemImage: "square.stack.3d.up",
                                       description: Text("Choose an MCAT subject to start studying."))
            }
        }
        .navigationSplitViewStyle(.balanced)
        .tint(.ankiBlue)
    }
}

struct SubjectRow: View {
    let deck: Deck

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: deck.systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(deck.tint, in: RoundedRectangle(cornerRadius: 8))

            Text(deck.name).font(.system(size: 16, weight: .medium))

            Spacer(minLength: 8)

            DeckCounts(deck: deck)
        }
        .padding(.vertical, 4)
    }
}

/// Colored New / Learn / Due counts (blue / red / green), matching Anki.
struct DeckCounts: View {
    let deck: Deck
    var body: some View {
        HStack(spacing: 8) {
            value(deck.new, .ankiNew)
            value(deck.learn, .ankiLearn)
            value(deck.due, .ankiDue)
        }
        .font(.system(size: 15, weight: .bold).monospacedDigit())
    }

    private func value(_ n: Int, _ color: Color) -> some View {
        Text("\(n)").foregroundStyle(n == 0 ? Color.ankiFaint : color)
    }
}

#Preview {
    RootView()
}
