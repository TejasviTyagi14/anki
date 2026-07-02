import SwiftUI

/// A study subject (Anki "deck"), reused for the iPad sidebar.
struct Deck: Identifiable {
    let id = UUID()
    var name: String
    var systemImage: String
    var tint: Color
    var new: Int
    var learn: Int
    var due: Int
    var studyable: Bool { new + learn + due > 0 }
}

struct FlashCard: Identifiable {
    let id = UUID()
    var subject: String
    var prompt: String
    var answer: String
    var explanation: String
    /// Normalized-acceptable answers used to grade handwritten / typed input.
    var accepted: [String]
}

enum MCAT {
    static let subjects: [Deck] = [
        Deck(name: "Biochemistry", systemImage: "atom", tint: .ankiBlue, new: 18, learn: 6, due: 44),
        Deck(name: "Biology", systemImage: "leaf.fill", tint: Color(hex: 0x16a34a), new: 12, learn: 3, due: 51),
        Deck(name: "General Chemistry", systemImage: "flask.fill", tint: Color(hex: 0x0ea5e9), new: 9, learn: 4, due: 33),
        Deck(name: "Organic Chemistry", systemImage: "hexagon.fill", tint: Color(hex: 0xd97706), new: 22, learn: 5, due: 27),
        Deck(name: "Physics", systemImage: "bolt.fill", tint: Color(hex: 0x7c3aed), new: 7, learn: 2, due: 40),
        Deck(name: "Psych / Soc", systemImage: "brain.head.profile", tint: Color(hex: 0xdb2777), new: 15, learn: 1, due: 29),
    ]

    static let cards: [FlashCard] = [
        FlashCard(subject: "Biochemistry",
                  prompt: "Which enzyme unwinds the DNA double helix at the replication fork?",
                  answer: "Helicase",
                  explanation: "Helicase breaks the hydrogen bonds between complementary base pairs, separating the strands for replication.",
                  accepted: ["helicase", "dna helicase"]),
        FlashCard(subject: "Biochemistry",
                  prompt: "What is the net charge of an amino acid at its isoelectric point (pI)?",
                  answer: "Zero",
                  explanation: "At the pI the zwitterionic form predominates, so the positive and negative charges cancel to a net charge of 0.",
                  accepted: ["zero", "0", "neutral", "no charge"]),
        FlashCard(subject: "Biochemistry",
                  prompt: "Name the rate-limiting enzyme of glycolysis.",
                  answer: "Phosphofructokinase-1 (PFK-1)",
                  explanation: "PFK-1 catalyzes the committed step (fructose-6-phosphate → fructose-1,6-bisphosphate) and is the key regulatory point.",
                  accepted: ["pfk1", "pfk", "phosphofructokinase", "phosphofructokinase1"]),
        FlashCard(subject: "General Chemistry",
                  prompt: "What is the pH of a 0.001 M HCl solution?",
                  answer: "3",
                  explanation: "HCl is a strong acid, so [H⁺] = 10⁻³ M and pH = −log(10⁻³) = 3.",
                  accepted: ["3", "three", "ph3"]),
        FlashCard(subject: "Organic Chemistry",
                  prompt: "What term describes non-superimposable mirror-image stereoisomers?",
                  answer: "Enantiomers",
                  explanation: "Enantiomers are chiral mirror images; stereoisomers that are not mirror images are diastereomers.",
                  accepted: ["enantiomers", "enantiomer"]),
        FlashCard(subject: "Physics",
                  prompt: "Write the equation for translational kinetic energy.",
                  answer: "KE = ½mv²",
                  explanation: "Kinetic energy equals one-half the mass times the square of the speed.",
                  accepted: ["ke12mv2", "12mv2", "kineticenergy12mv2"]),
        FlashCard(subject: "Psych / Soc",
                  prompt: "Which hypothalamic nucleus is the body's master circadian pacemaker?",
                  answer: "Suprachiasmatic nucleus (SCN)",
                  explanation: "The SCN is entrained by light via the retinohypothalamic tract and coordinates circadian rhythm.",
                  accepted: ["scn", "suprachiasmaticnucleus", "suprachiasmatic"]),
        FlashCard(subject: "Biochemistry",
                  prompt: "The Michaelis constant (Km) equals the substrate concentration at what fraction of Vmax?",
                  answer: "One-half (½ Vmax)",
                  explanation: "By definition Km is the [S] at which reaction velocity is half of Vmax.",
                  accepted: ["half", "onehalf", "12", "05", "50"]),
        FlashCard(subject: "Biochemistry",
                  prompt: "Which organelle is the primary site of ATP synthesis?",
                  answer: "Mitochondria",
                  explanation: "Oxidative phosphorylation on the inner mitochondrial membrane produces the bulk of cellular ATP.",
                  accepted: ["mitochondria", "mitochondrion"]),
        FlashCard(subject: "General Chemistry",
                  prompt: "How many electrons completely fill a d subshell?",
                  answer: "10",
                  explanation: "A d subshell has 5 orbitals × 2 electrons = 10.",
                  accepted: ["10", "ten"]),
        FlashCard(subject: "General Chemistry",
                  prompt: "What type of bond holds two water molecules together?",
                  answer: "Hydrogen bond",
                  explanation: "Hydrogen bonding between the partial charges of O and H links water molecules.",
                  accepted: ["hydrogen", "hydrogenbond", "hbond"]),
        FlashCard(subject: "Organic Chemistry",
                  prompt: "Stereoisomers that differ at some, but not all, chiral centers are called ___?",
                  answer: "Diastereomers",
                  explanation: "Unlike enantiomers, diastereomers are not mirror images and have different physical properties.",
                  accepted: ["diastereomers", "diastereomer"]),
        FlashCard(subject: "Organic Chemistry",
                  prompt: "A strong IR absorption near 1700 cm⁻¹ indicates which functional group?",
                  answer: "Carbonyl (C=O)",
                  explanation: "The C=O stretch appears as a strong band around 1700 cm⁻¹.",
                  accepted: ["carbonyl", "co", "ketone", "aldehyde"]),
        FlashCard(subject: "Physics",
                  prompt: "What is the SI unit of force?",
                  answer: "Newton",
                  explanation: "1 newton = 1 kg·m/s², the force to accelerate 1 kg at 1 m/s².",
                  accepted: ["newton", "n", "newtons"]),
        FlashCard(subject: "Physics",
                  prompt: "What is the SI unit of frequency?",
                  answer: "Hertz",
                  explanation: "1 hertz = 1 cycle per second (s⁻¹).",
                  accepted: ["hertz", "hz"]),
        FlashCard(subject: "Biology",
                  prompt: "What is the site of protein synthesis in the cell?",
                  answer: "Ribosome",
                  explanation: "Ribosomes translate mRNA into polypeptide chains.",
                  accepted: ["ribosome", "ribosomes"]),
        FlashCard(subject: "Biology",
                  prompt: "Which nephron structure filters blood in the kidney?",
                  answer: "Glomerulus",
                  explanation: "The glomerulus is the capillary tuft where filtration into Bowman's capsule occurs.",
                  accepted: ["glomerulus"]),
        FlashCard(subject: "Psych / Soc",
                  prompt: "Which brain lobe is primarily responsible for processing vision?",
                  answer: "Occipital lobe",
                  explanation: "The primary visual cortex (V1) is located in the occipital lobe.",
                  accepted: ["occipital", "occipitallobe"]),
        FlashCard(subject: "Psych / Soc",
                  prompt: "Which neurotransmitter is central to the brain's reward pathway?",
                  answer: "Dopamine",
                  explanation: "The mesolimbic dopamine pathway underlies reward and reinforcement.",
                  accepted: ["dopamine", "da"]),
    ]

    static func cards(for subject: String) -> [FlashCard] {
        let filtered = cards.filter { $0.subject == subject }
        return filtered.isEmpty ? cards : filtered
    }
}

/// Strip everything except letters/digits and lowercase, so handwriting/typing
/// variations ("PFK-1", "pfk 1", "PFK1") all compare equal.
func normalizeAnswer(_ s: String) -> String {
    s.lowercased().unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) }
        .map(String.init).joined()
}
