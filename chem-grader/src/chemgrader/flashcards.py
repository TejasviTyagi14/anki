"""Flashcard bank for the hand-drawn reaction grader.

Each card shows the student a short prompt (the "front"). The student draws the
answer on the back; a vision model then grades the drawing. The **answer key**
(``reference_answer`` prose + ``expected_smiles``) lives here on the server and
is *never* included in the client-facing :meth:`Flashcard.public` view, so the
browser can't leak it — the model receives it, the student does not.

This is deliberately separate from :mod:`chemgrader.problems` (the deterministic
RDKit drill grader): these cards target free-form drawing graded by an LLM, so
the reference is written as rich natural-language guidance rather than a single
SMILES string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Flashcard:
    id: str
    title: str  # short label for the picker
    mechanism: str  # topic tag, e.g. "SN1", "E2", "Diels-Alder"
    statement: str  # the card FRONT shown to the student
    reference_answer: str  # HIDDEN answer key (prose) sent only to the grader model
    expected_smiles: list[str] = field(default_factory=list)  # HIDDEN, for the RDKit check
    stereo_required: bool = False  # whether stereochemistry is graded

    def public(self) -> dict:
        """Client-safe view — no answer key, no expected SMILES."""
        return {
            "id": self.id,
            "title": self.title,
            "mechanism": self.mechanism,
            "statement": self.statement,
            "stereo_required": self.stereo_required,
        }


# The bank. Reference answers name the major product, give SMILES, state the
# mechanism in a sentence or two, and call out the specific wrong answers
# students give — that specificity is what makes the grading accurate.
FLASHCARDS: list[Flashcard] = [
    Flashcard(
        id="sn1-water",
        title="SN1: tertiary halide + H₂O",
        mechanism="SN1",
        statement=(
            "SN1 with a tertiary alkyl halide and water.\n\n"
            "tert-Butyl bromide, (CH₃)₃C–Br, is dissolved in water. "
            "Draw the major substitution product."
        ),
        reference_answer=(
            "Major product: tert-butanol, 2-methylpropan-2-ol, (CH₃)₃C–OH, SMILES CC(C)(C)O "
            "(C4H10O). Mechanism: unimolecular nucleophilic substitution (SN1). The C–Br "
            "bond ionizes first to give a stabilized tertiary carbocation (CH₃)₃C⁺; water "
            "then attacks the planar cation, and loss of a proton from the resulting "
            "oxocarbenium/oxonium gives the neutral alcohol. Rate depends only on the "
            "substrate (first order). No inversion/retention preference — the carbocation is "
            "planar, so stereochemistry is not the point here.\n"
            "Common student mistakes: (1) drawing the ELIMINATION alkene isobutylene "
            "CC(C)=C — that is the E1 byproduct, not the substitution product asked for; "
            "(2) leaving the bromide in the product or drawing an ether/ester; (3) writing a "
            "primary alcohol by moving the OH to a methyl (skeleton must stay tert-butyl); "
            "(4) forgetting to remove the + charge / drawing the bare carbocation as the "
            "final answer. A correct answer is the neutral tertiary alcohol with the carbon "
            "skeleton unchanged and OH where Br used to be."
        ),
        expected_smiles=["CC(C)(C)O"],
    ),
    Flashcard(
        id="hbr-markovnikov",
        title="HBr addition (Markovnikov)",
        mechanism="Electrophilic addition",
        statement=(
            "Propene (CH₃–CH=CH₂) reacts with HBr (no peroxides).\n\n"
            "Draw the major product."
        ),
        reference_answer=(
            "Major product: 2-bromopropane, CH₃CHBrCH₃, SMILES CC(Br)C (C3H7Br). Mechanism: "
            "electrophilic addition following Markovnikov's rule. H⁺ adds to the terminal "
            "CH₂ to give the more stable SECONDARY carbocation at C2; bromide then traps it, "
            "so Br ends up on the more substituted carbon. Common mistakes: drawing "
            "1-bromopropane CCCBr (anti-Markovnikov) — that is the RADICAL/peroxide product "
            "and is wrong without ROOR; adding H and Br to the same carbon; or retaining the "
            "double bond. Correct answer has Br on the central carbon."
        ),
        expected_smiles=["CC(Br)C"],
    ),
    Flashcard(
        id="hbr-peroxides",
        title="HBr addition (anti-Markovnikov)",
        mechanism="Radical addition",
        statement=(
            "Propene (CH₃–CH=CH₂) reacts with HBr in the presence of peroxides (ROOR).\n\n"
            "Draw the major product."
        ),
        reference_answer=(
            "Major product: 1-bromopropane, CH₃CH₂CH₂Br, SMILES CCCBr (C3H7Br). Mechanism: "
            "radical chain addition (peroxide effect). A Br• radical adds to the terminal "
            "carbon to give the more stable SECONDARY carbon radical, so Br ends up on the "
            "LESS substituted (terminal) carbon — anti-Markovnikov regiochemistry, the "
            "opposite of ionic HBr addition. Common mistakes: drawing 2-bromopropane "
            "CC(Br)C (that is the Markovnikov product, correct only WITHOUT peroxides); "
            "keeping the alkene; or adding two bromines. Correct answer is the primary "
            "bromide."
        ),
        expected_smiles=["CCCBr"],
    ),
    Flashcard(
        id="sn2-inversion",
        title="SN2 with inversion",
        mechanism="SN2",
        statement=(
            "(R)-2-bromobutane reacts with NaOH.\n\n"
            "Draw the product, showing stereochemistry with wedge/dash bonds."
        ),
        reference_answer=(
            "Major product: (S)-butan-2-ol, SMILES C[C@@H](O)CC (constitution CCC(O)C, "
            "C4H10O). Mechanism: bimolecular nucleophilic substitution (SN2). Hydroxide "
            "attacks the stereocenter from the face opposite the leaving bromide in one "
            "concerted step, so the configuration INVERTS (Walden inversion): (R) substrate "
            "gives (S) product. Because a priority change accompanies the swap, students "
            "must actually show the inverted wedge/dash arrangement, not just replace Br "
            "with OH in place. Common mistakes: (1) retaining configuration (drawing OH on "
            "the same wedge Br was on) — this is the single most common error and should "
            "cost significant credit when stereochemistry is requested; (2) an elimination "
            "product (but-2-ene / but-1-ene); (3) correct connectivity CCC(O)C but no "
            "stereochemistry shown — partial credit, note the missing inversion. Accept "
            "either enantiomer only if the drawing is racemic AND flag that SN2 is "
            "stereospecific."
        ),
        expected_smiles=["CCC(O)C"],
        stereo_required=True,
    ),
    Flashcard(
        id="sn1-solvolysis",
        title="SN1 solvolysis in methanol",
        mechanism="SN1",
        statement=(
            "tert-Butyl bromide, (CH₃)₃C–Br, is refluxed in methanol (CH₃OH).\n\n"
            "Draw the major substitution product."
        ),
        reference_answer=(
            "Major product: tert-butyl methyl ether (MTBE), (CH₃)₃C–O–CH₃, SMILES "
            "COC(C)(C)C (C5H12O). Mechanism: SN1 solvolysis. The tertiary C–Br ionizes to a "
            "tert-butyl carbocation; methanol (the solvent nucleophile) attacks, then loss "
            "of H⁺ from the oxonium gives the neutral ether. Common mistakes: drawing "
            "tert-butanol CC(C)(C)O (that would need water, not methanol) — wrong "
            "nucleophile; drawing the E1 alkene CC(C)=C; leaving a + charge or the bromide "
            "in the product; or forming a C–C bond to methanol instead of C–O. Correct "
            "answer is the ether with an OCH₃ where Br was."
        ),
        expected_smiles=["COC(C)(C)C"],
    ),
    Flashcard(
        id="e2-zaitsev",
        title="E2 (Zaitsev alkene)",
        mechanism="E2",
        statement=(
            "2-bromo-2,3-dimethylbutane reacts with sodium ethoxide (NaOEt).\n\n"
            "Draw the major elimination product."
        ),
        reference_answer=(
            "Major product: 2,3-dimethylbut-2-ene, (CH₃)₂C=C(CH₃)₂, SMILES CC(C)=C(C)C "
            "(C6H12). Mechanism: bimolecular elimination (E2). Ethoxide removes a "
            "β-hydrogen anti-periplanar to the leaving bromide in one concerted step; with a "
            "strong small base the more substituted (Zaitsev) tetrasubstituted alkene "
            "dominates. Common mistakes: drawing the less-substituted (Hofmann) alkene "
            "CC(C)(Br)... → C=C at the terminal position, i.e. 2,3-dimethylbut-1-ene "
            "CC(C)C(=C)C (minor here, favored only with bulky bases); drawing a substitution "
            "product (ether/alcohol); or keeping the bromine. Correct answer is the "
            "internal, fully substituted alkene."
        ),
        expected_smiles=["CC(C)=C(C)C"],
    ),
    Flashcard(
        id="hydroboration",
        title="Hydroboration–oxidation",
        mechanism="Hydroboration",
        statement=(
            "1-methylcyclohexene is treated with BH₃·THF, then H₂O₂ / NaOH.\n\n"
            "Draw the major product."
        ),
        reference_answer=(
            "Major product: trans-2-methylcyclohexan-1-ol, SMILES CC1CCCCC1O (constitution; "
            "C7H14O). Mechanism: hydroboration–oxidation gives net anti-Markovnikov, syn "
            "addition of H and OH across the alkene. Boron (then OH) adds to the LESS "
            "substituted alkene carbon, so the OH ends up on the carbon that was CH of the "
            "alkene, i.e. adjacent to the methyl-bearing carbon — giving 2-methylcyclohexanol, "
            "NOT 1-methylcyclohexanol. Syn addition places H and OH on the same face; on the "
            "ring the OH and the methyl end up trans to each other. Racemic (both "
            "enantiomers) is fine. Common mistakes: putting OH on the more substituted carbon "
            "(that is the Markovnikov/acid-hydration answer, 1-methylcyclohexanol "
            "CC1(O)CCCCC1) — the classic error; wrong (cis) relative stereochemistry; or "
            "over-oxidizing to a ketone. Correct answer is 2-methylcyclohexanol."
        ),
        expected_smiles=["CC1CCCCC1O"],
    ),
    Flashcard(
        id="diels-alder",
        title="Diels–Alder cycloaddition",
        mechanism="Diels-Alder",
        statement=(
            "1,3-butadiene reacts with maleic anhydride (a [4+2] cycloaddition).\n\n"
            "Draw the cycloadduct."
        ),
        reference_answer=(
            "Major product: the cis-fused bicyclic anhydride cis-1,2,3,6-"
            "tetrahydrophthalic anhydride, SMILES O=C1OC(=O)C2CCC=CC12 (C8H8O3). Mechanism: "
            "Diels–Alder [4+2] cycloaddition. The s-cis diene and the electron-poor "
            "dienophile (maleic anhydride) form two new C–C sigma bonds in one concerted, "
            "suprafacial step; a new six-membered ring bearing ONE double bond (between the "
            "former C2–C3 of the diene) is created, fused to the anhydride ring. The ring "
            "fusion is cis (substituents from the dienophile stay cis). Common mistakes: "
            "forgetting the residual ring double bond, or putting it in the wrong place; "
            "opening the anhydride; forming only one bond; or trans ring fusion. Correct "
            "answer is the bicyclic cyclohexene cis-fused to the anhydride."
        ),
        expected_smiles=["O=C1OC(=O)C2CCC=CC12"],
    ),
    Flashcard(
        id="grignard",
        title="Grignard + ketone",
        mechanism="Nucleophilic addition",
        statement=(
            "Phenylmagnesium bromide (PhMgBr) is added to acetone, then worked up with "
            "aqueous acid (H₃O⁺).\n\nDraw the product."
        ),
        reference_answer=(
            "Major product: 2-phenylpropan-2-ol, SMILES CC(C)(O)c1ccccc1 (C9H12O). "
            "Mechanism: nucleophilic addition of a Grignard reagent to a ketone. The "
            "carbanion-like phenyl adds to the electrophilic carbonyl carbon of acetone, "
            "giving a magnesium alkoxide; aqueous acid protonates it to the tertiary "
            "alcohol. A ketone + Grignard always gives a 3° alcohol. Common mistakes: not "
            "forming the new C–C bond to the phenyl (drawing acetone reduced to isopropanol "
            "CC(O)C); leaving a C=O in the product (the carbonyl is consumed); attaching "
            "the oxygen to the ring; or forgetting the acidic workup and leaving an alkoxide "
            "salt. Correct answer is the tertiary benzylic alcohol."
        ),
        expected_smiles=["CC(C)(O)c1ccccc1"],
    ),
    Flashcard(
        id="pcc-oxidation",
        title="PCC oxidation",
        mechanism="Oxidation",
        statement=(
            "1-butanol (CH₃CH₂CH₂CH₂OH) is treated with PCC in dichloromethane.\n\n"
            "Draw the product."
        ),
        reference_answer=(
            "Major product: butanal, CH₃CH₂CH₂CHO, SMILES CCCC=O (C4H8O). Mechanism: PCC is "
            "a mild Cr(VI) oxidant that oxidizes a primary alcohol to the ALDEHYDE and stops "
            "there (anhydrous conditions, no over-oxidation). Common mistakes: over-oxidizing "
            "to butanoic acid CCCC(=O)O — that requires a stronger aqueous oxidant like "
            "Jones/KMnO₄, and is the single most common error with PCC; drawing a ketone "
            "(wrong — oxidation of a 1° alcohol gives an aldehyde, the carbon skeleton is "
            "unchanged); or leaving the alcohol untouched. Correct answer is the aldehyde."
        ),
        expected_smiles=["CCCC=O"],
    ),
    Flashcard(
        id="carbocation-rearrangement",
        title="Carbocation rearrangement",
        mechanism="Electrophilic addition + hydride shift",
        statement=(
            "3-methylbut-1-ene (CH₂=CH–CH(CH₃)₂) reacts with HCl.\n\n"
            "Draw the major product."
        ),
        reference_answer=(
            "Major product: 2-chloro-2-methylbutane, SMILES CCC(C)(C)Cl (C5H11Cl). "
            "Mechanism: electrophilic addition with a 1,2-hydride shift. H⁺ adds to the "
            "terminal alkene carbon to give a SECONDARY carbocation; a hydride shifts from "
            "the adjacent CH(CH₃)₂ to form a more stable TERTIARY carbocation; chloride then "
            "traps the tertiary cation. Common mistakes: giving the un-rearranged "
            "Markovnikov product 2-chloro-3-methylbutane CC(Cl)C(C)C (secondary chloride — "
            "the classic 'forgot the rearrangement' error); anti-Markovnikov addition; or "
            "keeping the double bond. Correct answer is the tertiary chloride after the "
            "hydride shift."
        ),
        expected_smiles=["CCC(C)(C)Cl"],
    ),
]

_BY_ID = {c.id: c for c in FLASHCARDS}


def get_flashcard(card_id: str) -> Optional[Flashcard]:
    return _BY_ID.get(card_id)
