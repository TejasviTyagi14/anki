/*
 * <MoleculeEditor> — reusable skeletal-structure editor (React + SVG).
 * Exposed as window.MoleculeEditor so both the standalone builder page and the
 * grader app can use it (compiled per-page with esbuild; React is a global).
 *
 * Props:
 *   onMolecule({ molecule, smiles, formula, name, valid })  — called on every change
 *   (smiles/formula/name resolved from the same-origin backend; null while empty/invalid)
 *
 * Interaction: click = add atom · drag between atoms = bond (30/120 deg snap) ·
 * drag onto an atom = close ring · click bond = cycle order · click atom = select ·
 * eraser removes · element dropdown changes the selected atom.
 */
const { useState, useReducer, useRef, useEffect } = React;

const ELEMENTS = ["C", "O", "N", "H", "S", "P", "F", "Cl", "Br", "I"];
const VALENCE = { C: 4, N: 3, O: 2, S: 2, P: 3, F: 1, Cl: 1, Br: 1, I: 1, H: 1 };
const COLORS = { C: "#1f2937", O: "#dc2626", N: "#2563eb", S: "#b45309", P: "#c026d3", F: "#0d9488", Cl: "#16a34a", Br: "#a16207", I: "#7c3aed", H: "#6b7280" };
const BOND_LEN = 46, ATOM_HIT_R = 17, SNAP_ATOM_R = 26, MOVE_EPS = 4;

const EMPTY = { atoms: [], bonds: [], nextId: 1 };
const initialHistory = { past: [], present: EMPTY, future: [] };
function historyReducer(state, action) {
  switch (action.type) {
    case "commit": return { past: [...state.past, state.present].slice(-200), present: action.present, future: [] };
    case "undo": return state.past.length ? { past: state.past.slice(0, -1), present: state.past[state.past.length - 1], future: [state.present, ...state.future] } : state;
    case "redo": return state.future.length ? { past: [...state.past, state.present], present: state.future[0], future: state.future.slice(1) } : state;
    case "clear": return (state.present.atoms.length || state.present.bonds.length) ? { past: [...state.past, state.present], present: EMPTY, future: [] } : state;
    default: return state;
  }
}
function snapAngle(from, to, len) {
  let ang = Math.atan2(to.y - from.y, to.x - from.x);
  const step = Math.PI / 6;
  ang = Math.round(ang / step) * step;
  return { x: from.x + len * Math.cos(ang), y: from.y + len * Math.sin(ang) };
}
function distToSeg(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy || 1;
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}
function moleculeJSON(mol) {
  return {
    atoms: mol.atoms.map((a) => ({ id: a.id, element: a.el, x: Math.round(a.x * 10) / 10, y: Math.round(a.y * 10) / 10 })),
    bonds: mol.bonds.map((b) => ({ a: b.a, b: b.b, order: b.order })),
  };
}
function toMolblock(mol) {
  const idx = new Map(mol.atoms.map((a, i) => [a.id, i + 1]));
  const pad3 = (n) => String(n).padStart(3, " ");
  const f10 = (v) => v.toFixed(4).padStart(10, " ");
  const L = ["", "  chemgrader", ""];
  L.push(pad3(mol.atoms.length) + pad3(mol.bonds.length) + "  0  0  0  0  0  0  0  0999 V2000");
  for (const a of mol.atoms) L.push(f10(a.x / 40) + f10(-a.y / 40) + f10(0) + " " + a.el.padEnd(3, " ") + " 0  0  0  0  0  0  0  0  0  0  0  0");
  for (const b of mol.bonds) L.push(pad3(idx.get(b.a)) + pad3(idx.get(b.b)) + pad3(b.order) + pad3(0));
  L.push("M  END");
  return L.join("\n") + "\n";
}

const Icon = ({ d, filled }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const IconPencil = <Icon d={<path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5z" />} />;
const IconEraser = <Icon d={<><path d="M20 20H7L3 16a2 2 0 010-3l9-9 8 8-6 6" /><path d="M11 7l6 6" /></>} />;
const IconUndo = <Icon d={<path d="M9 14L4 9l5-5M4 9h11a5 5 0 010 10h-3" />} />;
const IconRedo = <Icon d={<path d="M15 14l5-5-5-5M20 9H9a5 5 0 000 10h3" />} />;
const IconTrash = <Icon d={<><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M6 6l1 14a2 2 0 002 2h6a2 2 0 002-2l1-14" /></>} />;

function MoleculeEditor({ onMolecule }) {
  const [hist, dispatch] = useReducer(historyReducer, initialHistory);
  const mol = hist.present;
  const [tool, setTool] = useState("draw");
  const [element, setElement] = useState("C");
  const [selected, setSelected] = useState(null);
  const [hoverAtom, setHoverAtom] = useState(null);
  const [hoverBond, setHoverBond] = useState(null);
  const [drag, setDrag] = useState(null);
  const [preview, setPreview] = useState(null);
  const [readout, setReadout] = useState(null);
  const svgRef = useRef(null);
  const cbRef = useRef(onMolecule);
  cbRef.current = onMolecule;

  const commit = (present) => dispatch({ type: "commit", present });
  const atomById = (id) => mol.atoms.find((a) => a.id === id);
  const bondSumOf = (id) => mol.bonds.filter((b) => b.a === id || b.b === id).reduce((s, b) => s + b.order, 0);
  const degree = (id) => mol.bonds.filter((b) => b.a === id || b.b === id).length;

  const findAtom = (p) => { let best = null, bd = ATOM_HIT_R; for (const a of mol.atoms) { const d = Math.hypot(a.x - p.x, a.y - p.y); if (d <= bd) { bd = d; best = a; } } return best; };
  const findBond = (p) => { for (const b of mol.bonds) { const a = atomById(b.a), c = atomById(b.b); if (a && c && distToSeg(p, a, c) < 8) return b; } return null; };
  const snapPreview = (fromPt, p, excludeId) => {
    let near = null, nd = SNAP_ATOM_R;
    for (const a of mol.atoms) { if (a.id === excludeId) continue; const d = Math.hypot(a.x - p.x, a.y - p.y); if (d <= nd) { nd = d; near = a; } }
    if (near) return { to: { x: near.x, y: near.y }, snapId: near.id };
    return { to: snapAngle(fromPt, p, BOND_LEN), snapId: null };
  };
  const clientToSvg = (cx, cy) => { const pt = svgRef.current.createSVGPoint(); pt.x = cx; pt.y = cy; return pt.matrixTransform(svgRef.current.getScreenCTM().inverse()); };

  const placeAtom = (pos) => { const id = mol.nextId; commit({ atoms: [...mol.atoms, { id, el: element, x: pos.x, y: pos.y }], bonds: mol.bonds, nextId: id + 1 }); setSelected(id); };
  const cycleBond = (bid) => commit({ ...mol, bonds: mol.bonds.map((b) => (b.id === bid ? { ...b, order: (b.order % 3) + 1 } : b)) });
  const deleteAtom = (id) => commit({ atoms: mol.atoms.filter((a) => a.id !== id), bonds: mol.bonds.filter((b) => b.a !== id && b.b !== id), nextId: mol.nextId });
  const deleteBond = (bid) => commit({ ...mol, bonds: mol.bonds.filter((b) => b.id !== bid) });
  const changeElement = (id, el) => commit({ ...mol, atoms: mol.atoms.map((a) => (a.id === id ? { ...a, el } : a)) });

  const commitBondDrag = (p) => {
    let atoms = mol.atoms.slice(), bonds = mol.bonds.slice(), nextId = mol.nextId;
    let startId = drag.fromId;
    if (startId == null) { startId = nextId; atoms.push({ id: nextId, el: element, x: drag.start.x, y: drag.start.y }); nextId++; }
    const fromPt = drag.fromId != null ? atomById(drag.fromId) : drag.start;
    const snap = preview || snapPreview(fromPt, p, drag.fromId);
    let endId;
    if (snap.snapId != null && snap.snapId !== startId) endId = snap.snapId;
    else { endId = nextId; atoms.push({ id: nextId, el: element, x: snap.to.x, y: snap.to.y }); nextId++; }
    if (startId === endId) return;
    const ex = bonds.find((b) => (b.a === startId && b.b === endId) || (b.a === endId && b.b === startId));
    if (ex) bonds = bonds.map((b) => (b === ex ? { ...b, order: (b.order % 3) + 1 } : b));
    else bonds = [...bonds, { id: nextId++, a: startId, b: endId, order: 1 }];
    commit({ atoms, bonds, nextId });
    setSelected(endId);
  };

  const onPointerDown = (e) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = clientToSvg(e.clientX, e.clientY);
    const a = findAtom(p), b = a ? null : findBond(p);
    if (tool === "erase") { if (a) deleteAtom(a.id); else if (b) deleteBond(b.id); return; }
    setDrag({ fromId: a ? a.id : null, downBond: b ? b.id : null, start: p, moved: false });
  };
  const onPointerMove = (e) => {
    const p = clientToSvg(e.clientX, e.clientY);
    if (drag) {
      const moved = Math.hypot(p.x - drag.start.x, p.y - drag.start.y) > MOVE_EPS;
      if (moved && drag.downBond == null) setPreview(snapPreview(drag.fromId != null ? atomById(drag.fromId) : drag.start, p, drag.fromId));
      else setPreview(null);
      if (moved !== drag.moved) setDrag({ ...drag, moved });
    } else {
      const a = findAtom(p);
      setHoverAtom(a ? a.id : null);
      setHoverBond(a ? null : (findBond(p) ? findBond(p).id : null));
    }
  };
  const onPointerUp = (e) => {
    if (!drag) return;
    const p = clientToSvg(e.clientX, e.clientY);
    if (tool === "draw") {
      if (!drag.moved) {
        if (drag.fromId != null) { setSelected(drag.fromId); const a = atomById(drag.fromId); if (a) setElement(a.el); }
        else if (drag.downBond != null) cycleBond(drag.downBond);
        else placeAtom(drag.start);
      } else if (drag.downBond == null) commitBondDrag(p);
    }
    setDrag(null); setPreview(null);
  };
  const onPickElement = (el) => { setElement(el); if (selected != null) changeElement(selected, el); };

  useEffect(() => {
    const onKey = (e) => {
      const k = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && k === "z") { e.preventDefault(); dispatch({ type: e.shiftKey ? "redo" : "undo" }); }
      else if ((e.metaKey || e.ctrlKey) && k === "y") { e.preventDefault(); dispatch({ type: "redo" }); }
      else if ((e.key === "Backspace" || e.key === "Delete") && selected != null) { e.preventDefault(); deleteAtom(selected); setSelected(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, mol]);

  // resolve SMILES/formula from the backend and report molecule up
  useEffect(() => {
    const molecule = moleculeJSON(mol);
    if (mol.atoms.length === 0) { setReadout(null); if (cbRef.current) cbRef.current({ molecule, smiles: null, valid: false }); return; }
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const r = await fetch(location.origin + "/structure/from-input", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source: "molblock", payload: { molblock: toMolblock(mol) } }) });
        if (!r.ok) throw new Error(((await r.json()).detail) || "invalid structure");
        const { smiles } = await r.json();
        const info = await (await fetch(location.origin + "/structure/canonical", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ smiles, with_name: true }) })).json();
        if (!alive) return;
        setReadout({ smiles: info.canonical_smiles, formula: info.formula, name: info.iupac_name });
        if (cbRef.current) cbRef.current({ molecule, smiles: info.canonical_smiles, formula: info.formula, name: info.iupac_name, valid: true });
      } catch (err) {
        if (!alive) return;
        setReadout({ error: err.message });
        if (cbRef.current) cbRef.current({ molecule, smiles: null, valid: false, error: err.message });
      }
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [mol]);

  const isLabeled = (a) => a.el !== "C";
  const labelFor = (a) => { const h = Math.max(0, (VALENCE[a.el] || 0) - bondSumOf(a.id)); return a.el + (h > 0 ? "H" + (h > 1 ? h : "") : ""); };
  const line = (x1, y1, x2, y2, cls, stroke) => <line x1={x1} y1={y1} x2={x2} y2={y2} className={cls} stroke={stroke} />;

  const renderBond = (b) => {
    const a = atomById(b.a), c = atomById(b.b); if (!a || !c) return null;
    const len = Math.hypot(c.x - a.x, c.y - a.y) || 1, ux = (c.x - a.x) / len, uy = (c.y - a.y) / len;
    const A = { x: a.x + (isLabeled(a) ? ux * 13 : 0), y: a.y + (isLabeled(a) ? uy * 13 : 0) };
    const C = { x: c.x - (isLabeled(c) ? ux * 13 : 0), y: c.y - (isLabeled(c) ? uy * 13 : 0) };
    const px = -uy, py = ux, offs = b.order === 1 ? [0] : b.order === 2 ? [-2.8, 2.8] : [-4.6, 0, 4.6];
    const hot = hoverBond === b.id;
    return (
      <g key={"b" + b.id}>
        {offs.map((o, i) => line(A.x + px * o, A.y + py * o, C.x + px * o, C.y + py * o, "mbe-bond", hot ? "#2563eb" : "#111827"))}
        {line(a.x, a.y, c.x, c.y, "mbe-bond-hit")}
      </g>
    );
  };
  const renderAtom = (a) => {
    const sel = selected === a.id, hov = hoverAtom === a.id;
    return (
      <g key={"a" + a.id}>
        {sel && <circle cx={a.x} cy={a.y} r={15} className="mbe-sel" />}
        {hov && !sel && <circle cx={a.x} cy={a.y} r={14} className="mbe-hover" />}
        {isLabeled(a) ? (<><circle cx={a.x} cy={a.y} r={12} fill="#fff" /><text x={a.x} y={a.y} className="mbe-label" fill={COLORS[a.el] || "#111827"}>{labelFor(a)}</text></>)
          : (degree(a.id) === 0 && <circle cx={a.x} cy={a.y} r={3.2} fill="#111827" />)}
        <circle cx={a.x} cy={a.y} r={ATOM_HIT_R} className="mbe-atom-hit" />
      </g>
    );
  };

  const selectedEl = selected != null && atomById(selected) ? atomById(selected).el : element;
  return (
    <div className="mbe-root">
      <div className="mbe-toolbar" role="toolbar" aria-label="Drawing tools">
        <button type="button" className="mbe-tool" aria-label="Draw" aria-pressed={tool === "draw"} onClick={() => setTool("draw")}>{IconPencil}</button>
        <button type="button" className="mbe-tool" aria-label="Eraser" aria-pressed={tool === "erase"} onClick={() => setTool("erase")}>{IconEraser}</button>
        <span className="mbe-div" />
        <label className="sr-only" htmlFor="mbe-el">Element for the selected atom</label>
        <select id="mbe-el" className="mbe-el" value={selectedEl} onChange={(e) => onPickElement(e.target.value)} aria-label="Element">
          {ELEMENTS.map((el) => <option key={el} value={el}>{el}</option>)}
        </select>
        <span className="mbe-div" />
        <button type="button" className="mbe-tool" aria-label="Undo" disabled={!hist.past.length} onClick={() => dispatch({ type: "undo" })}>{IconUndo}</button>
        <button type="button" className="mbe-tool" aria-label="Redo" disabled={!hist.future.length} onClick={() => dispatch({ type: "redo" })}>{IconRedo}</button>
        <button type="button" className="mbe-tool" aria-label="Clear" disabled={!mol.atoms.length} onClick={() => { dispatch({ type: "clear" }); setSelected(null); }}>{IconTrash}</button>
      </div>
      <svg ref={svgRef} className={"mbe-canvas" + (tool === "erase" ? " is-erase" : "")} viewBox="0 0 960 620" preserveAspectRatio="xMidYMid meet"
        role="application" aria-label="Molecule drawing canvas. Click to add an atom, drag between atoms to bond."
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={() => { setHoverAtom(null); setHoverBond(null); }}>
        {mol.bonds.map(renderBond)}
        {preview && line(drag.fromId != null ? atomById(drag.fromId).x : drag.start.x, drag.fromId != null ? atomById(drag.fromId).y : drag.start.y, preview.to.x, preview.to.y, "mbe-preview")}
        {preview && preview.snapId != null && <circle cx={atomById(preview.snapId).x} cy={atomById(preview.snapId).y} r={16} className="mbe-snap" />}
        {mol.atoms.map(renderAtom)}
      </svg>
      <div className={"mbe-readout" + (readout && readout.error ? " err" : readout ? " ok" : "")} aria-live="polite">
        {readout == null ? "Draw a structure — click to place an atom, drag to bond."
          : readout.error ? "⚠ " + readout.error
          : (<><b>{readout.smiles}</b>{" · " + readout.formula}{readout.name ? " · " + readout.name : ""}</>)}
      </div>
    </div>
  );
}

window.MoleculeEditor = MoleculeEditor;
