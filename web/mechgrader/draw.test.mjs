// Node test for the framework-free drawer's graph -> SMILES logic (DOM-free).
// Run: out/extracted/node/bin/node web/mechgrader/draw.test.mjs
import { graphToSmiles, graphToFormula } from "./draw.js";

let pass = 0, fail = 0;
const eq = (name, got, want) => {
  if (got === want) { pass++; console.log("ok ", name, "->", got); }
  else { fail++; console.error("FAIL", name, "got", JSON.stringify(got), "want", JSON.stringify(want)); }
};

eq("ethanol", graphToSmiles([{ id: 1, el: "C" }, { id: 2, el: "C" }, { id: 3, el: "O" }],
  [{ a: 1, b: 2, order: 1 }, { a: 2, b: 3, order: 1 }]), "CCO");
eq("formaldehyde", graphToSmiles([{ id: 1, el: "C" }, { id: 2, el: "O" }], [{ a: 1, b: 2, order: 2 }]), "C=O");
eq("hydroxide", graphToSmiles([{ id: 1, el: "O", charge: -1 }], []), "[OH-]");
eq("two-fragment", graphToSmiles(
  [{ id: 1, el: "O", charge: -1 }, { id: 2, el: "C" }, { id: 3, el: "Br" }],
  [{ a: 2, b: 3, order: 1 }]), "[OH-].CBr");
eq("ethanol-formula", graphToFormula([{ id: 1, el: "C" }, { id: 2, el: "C" }, { id: 3, el: "O" }],
  [{ a: 1, b: 2, order: 1 }, { a: 2, b: 3, order: 1 }]), "C2H6O");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
