/**
 * mechanism.js — MechGrader's shared Mechanism/Step data model.
 *
 * Framework-free ES module. No DOM, no rendering — safe to import in Anki's
 * desktop reviewer webview, an Android WebView, or Node (for tests). This is the
 * ONE source of truth for what a mechanism *is*; every other file in the bundle
 * (arrows.js, editor.js, rdkit.js) reads/writes this shape.
 *
 * serialize()/deserialize() round-trip EXACTLY the JSON the grader and the
 * MechCard ReferenceMechanism use:
 *
 *   Mechanism = { "steps": [ Step, ... ] }
 *   Step = {
 *     "reactants": [ "<atom-mapped SMILES>", ... ],
 *     "arrows":    [ { "from": "<endpoint>", "to": "<endpoint>", "kind": "curved" }, ... ],
 *     "products":  [ "<atom-mapped SMILES>", ... ]
 *   }
 *
 * An arrow endpoint is one of:
 *   "atom:i"    an atom (electron sink/source) — 0-based atom index i
 *   "bond:i-j"  the bond between atoms i and j
 *   "lp:i"      a lone pair on atom i
 * where i / j are 0-based atom indices into the step's reactant(s). (This matches
 * chem-grader's README: arrow endpoints are atom:i / bond:i-j / lp:i.)
 */

/** Matches exactly one arrow-endpoint token. */
export const ENDPOINT_RE = /^(?:atom:\d+|bond:\d+-\d+|lp:\d+)$/;

/** True if `token` is a syntactically valid endpoint string. */
export function isValidEndpoint(token) {
  return typeof token === "string" && ENDPOINT_RE.test(token);
}

function asIndex(i) {
  const n = Number(i);
  if (!Number.isInteger(n) || n < 0) {
    throw new RangeError(`atom index must be a non-negative integer, got ${i}`);
  }
  return n;
}

/** Build an "atom:i" endpoint. */
export function atomEndpoint(i) {
  return `atom:${asIndex(i)}`;
}

/** Build an "lp:i" (lone-pair) endpoint. */
export function lonePairEndpoint(i) {
  return `lp:${asIndex(i)}`;
}

/** Build a "bond:i-j" endpoint (order-preserving; i then j). */
export function bondEndpoint(i, j) {
  return `bond:${asIndex(i)}-${asIndex(j)}`;
}

/**
 * Parse an endpoint token into a structured descriptor, or null if invalid.
 *   "atom:3"   -> { type: "atom", atoms: [3] }
 *   "bond:1-4" -> { type: "bond", atoms: [1, 4] }
 *   "lp:5"     -> { type: "lp",   atoms: [5] }
 */
export function parseEndpoint(token) {
  if (!isValidEndpoint(token)) return null;
  const colon = token.indexOf(":");
  const type = token.slice(0, colon);
  const rest = token.slice(colon + 1);
  if (type === "bond") {
    const [i, j] = rest.split("-").map(Number);
    return { type: "bond", atoms: [i, j] };
  }
  return { type, atoms: [Number(rest)] };
}

/**
 * Normalize any arrow-like value into exactly { from, to, kind }. Throws if the
 * endpoints are not valid — arrows are stored as *data first*, so we keep that
 * data clean at the boundary. `kind` defaults to "curved" (the only kind today).
 */
export function normalizeArrow(arrow) {
  if (!arrow || typeof arrow !== "object") {
    throw new TypeError("arrow must be an object with { from, to }");
  }
  const { from, to } = arrow;
  if (!isValidEndpoint(from)) throw new TypeError(`arrow.from is not a valid endpoint: ${JSON.stringify(from)}`);
  if (!isValidEndpoint(to)) throw new TypeError(`arrow.to is not a valid endpoint: ${JSON.stringify(to)}`);
  const kind = arrow.kind == null ? "curved" : String(arrow.kind);
  return { from, to, kind };
}

/** One mechanism step: reactants -> (arrows) -> products. */
export class Step {
  constructor(init = {}) {
    this.reactants = Array.isArray(init.reactants) ? init.reactants.map(String) : [];
    this.products = Array.isArray(init.products) ? init.products.map(String) : [];
    this.arrows = Array.isArray(init.arrows) ? init.arrows.map(normalizeArrow) : [];
  }

  // ---- reactants ----
  addReactant(smiles = "") {
    this.reactants.push(String(smiles));
    return this.reactants.length - 1;
  }
  setReactant(i, smiles) {
    if (i >= 0 && i < this.reactants.length) this.reactants[i] = String(smiles);
  }
  removeReactant(i) {
    if (i >= 0 && i < this.reactants.length) this.reactants.splice(i, 1);
  }

  // ---- products ----
  addProduct(smiles = "") {
    this.products.push(String(smiles));
    return this.products.length - 1;
  }
  setProduct(i, smiles) {
    if (i >= 0 && i < this.products.length) this.products[i] = String(smiles);
  }
  removeProduct(i) {
    if (i >= 0 && i < this.products.length) this.products.splice(i, 1);
  }

  // ---- arrows ----
  addArrow(arrow) {
    const a = normalizeArrow(arrow);
    this.arrows.push(a);
    return a;
  }
  removeArrow(i) {
    if (i >= 0 && i < this.arrows.length) this.arrows.splice(i, 1);
  }
  setArrows(list) {
    this.arrows = (list || []).map(normalizeArrow);
  }

  /** Produce EXACTLY { reactants, arrows:[{from,to,kind}], products }. */
  serialize() {
    return {
      reactants: this.reactants.map(String),
      arrows: this.arrows.map((a) => ({ from: a.from, to: a.to, kind: a.kind })),
      products: this.products.map(String),
    };
  }

  static deserialize(obj = {}) {
    return new Step(obj);
  }
}

/** A whole mechanism: an ordered list of steps. */
export class Mechanism {
  constructor(init = {}) {
    const steps = Array.isArray(init.steps) ? init.steps : [];
    this.steps = steps.map((s) => (s instanceof Step ? s : Step.deserialize(s)));
  }

  get length() {
    return this.steps.length;
  }

  step(i) {
    return this.steps[i] || null;
  }

  /** Append a step (accepts a Step, a plain object, or nothing for an empty step). */
  addStep(step) {
    const s = step instanceof Step ? step : new Step(step || {});
    this.steps.push(s);
    return s;
  }

  removeStep(i) {
    if (i >= 0 && i < this.steps.length) this.steps.splice(i, 1);
  }

  /** Produce EXACTLY { steps: [ Step, ... ] }. */
  serialize() {
    return { steps: this.steps.map((s) => s.serialize()) };
  }

  static deserialize(obj = {}) {
    return new Mechanism(obj);
  }

  /** So JSON.stringify(mechanism) also yields the canonical shape. */
  toJSON() {
    return this.serialize();
  }
}

export default Mechanism;
