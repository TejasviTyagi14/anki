import SwiftUI

/// Colors mirror Anki's real design tokens (ts/lib/sass/_vars.scss + card-counts.scss):
/// new = blue #3b82f6, learning = red #dc2626, review/due = green #16a34a, primary = blue.
extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xff) / 255.0,
            green: Double((hex >> 8) & 0xff) / 255.0,
            blue: Double(hex & 0xff) / 255.0
        )
    }

    static let ankiBlue = Color(hex: 0x3b82f6)
    static let ankiBlueDeep = Color(hex: 0x2563eb)
    static let ankiNew = Color(hex: 0x3b82f6)
    static let ankiLearn = Color(hex: 0xdc2626)
    static let ankiDue = Color(hex: 0x16a34a)
    static let ankiHard = Color(hex: 0xd97706)
    static let ankiEasy = Color(hex: 0x2563eb)
    static let ankiFaint = Color(hex: 0xb8bcc4)
}
