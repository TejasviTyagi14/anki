/*
 * Reaction Mechanism Grader — React shell.
 * Modes: Practice (SN1/SN2/E1/E2 drills) and Free build (arbitrary graphs).
 * Uses the shared <MoleculeEditor> (editor.js) in a modal. Backend/grading unchanged.
 */
const { useState, useEffect, useRef } = React;
const MoleculeEditor = window.MoleculeEditor;
const API = location.origin;

async function api(path, opts) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d; } catch (_) {} throw new Error(d); }
  return r.json();
}

// ---- read-only 2D depiction (self-hosted SmilesDrawer) ----
function Depiction({ smiles, w = 200, h = 110 }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext("2d"); if (ctx) ctx.clearRect(0, 0, c.width, c.height);
    if (!smiles || typeof SmilesDrawer === "undefined") return;
    try {
      const d = new SmilesDrawer.Drawer({ width: w, height: h, bondThickness: 1.1 });
      SmilesDrawer.parse(smiles, (t) => d.draw(t, c, "light", false), () => {});
    } catch (_) {}
  }, [smiles, w, h]);
  return <canvas ref={ref} width={w} height={h} className="depiction" role="img" aria-label={smiles ? "structure " + smiles : "structure"} />;
}

// ---- RDKit SVG depiction with atom/bond highlighting (backend-rendered) ----
function SvgDepiction({ smiles, highlightAtoms = [], highlightBonds = [], w = 240, h = 170, label }) {
  const [svg, setSvg] = useState("");
  const key = JSON.stringify([smiles, highlightAtoms, highlightBonds, w, h]);
  useEffect(() => {
    let alive = true;
    if (!smiles) { setSvg(""); return; }
    fetch(API + "/structure/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ smiles, highlight_atoms: highlightAtoms, highlight_bonds: highlightBonds, width: w, height: h }) })
      .then((r) => (r.ok ? r.text() : "")).then((t) => { if (alive) setSvg(t); }).catch(() => {});
    return () => { alive = false; };
  }, [key]);
  return <div className="svg-depiction" role="img" aria-label={label || ("structure " + (smiles || ""))} dangerouslySetInnerHTML={{ __html: svg }} />;
}

// ---- progressive "reveal expected answer" with a highlighted diff ----
function RevealPanel({ problemId, product }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const reveal = async () => {
    setLoading(true); setErr("");
    try {
      const ans = await api(`/problems/${problemId}/answer`);
      const expected = ans.products[0];
      const diff = await api("/structure/diff", { method: "POST", body: JSON.stringify({ a: product, b: expected }) });
      setData({ expected, diff });
    } catch (e) { setErr(e.message); }
    setLoading(false);
  };
  if (!data) {
    return (
      <div className="reveal">
        <button className="btn" onClick={reveal} disabled={loading}>{loading ? "Revealing…" : "Reveal expected answer"}</button>
        {err && <span className="fb-err" style={{ marginLeft: 8 }}>{err}</span>}
      </div>
    );
  }
  return (
    <div className="reveal">
      <div className="reveal-grid">
        <div className="reveal-box"><div className="rxn-cap">your product</div><SvgDepiction smiles={product} highlightAtoms={data.diff.changed_atoms_a} highlightBonds={data.diff.changed_bonds_a} label="your product, differences highlighted" /></div>
        <div className="reveal-box"><div className="rxn-cap">expected</div><SvgDepiction smiles={data.expected} highlightAtoms={data.diff.changed_atoms_b} highlightBonds={data.diff.changed_bonds_b} label="expected product, differences highlighted" /></div>
      </div>
      <div className="muted" style={{ fontSize: "var(--text-xs)" }}>
        {data.diff.same ? "Your structure matches the expected product — the issue is elsewhere (see the explanation above)." : "Highlighted atoms/bonds are where your structure differs from the expected one."}
      </div>
    </div>
  );
}

// ---- editor modal ----
function EditorModal({ title, onCancel, onUse }) {
  const [draft, setDraft] = useState(null);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal card">
        <div className="modal-head"><h3>{title}</h3><button className="btn btn-ghost" aria-label="Close editor" onClick={onCancel}>✕</button></div>
        <div className="modal-editor"><MoleculeEditor onMolecule={setDraft} /></div>
        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" disabled={!(draft && draft.smiles)} onClick={() => onUse(draft.smiles)}>Use structure</button>
        </div>
      </div>
    </div>
  );
}

// ---- feedback ----
function ScoreDial({ value, passed }) {
  const r = 32, circ = 2 * Math.PI * r, off = circ * (1 - Math.max(0, Math.min(1, value)));
  const col = passed ? "var(--ok)" : value >= 0.5 ? "var(--warn)" : "var(--err)";
  return (
    <div className="dial">
      <svg width="76" height="76" aria-hidden="true">
        <circle cx="38" cy="38" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="8" />
        <circle cx="38" cy="38" r={r} fill="none" stroke={col} strokeWidth="8" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off} />
      </svg>
      <div className="dial-num">{Math.round(value * 100)}%</div>
    </div>
  );
}

function Feedback({ result, grading, reveal }) {
  if (grading) return <section className="panel card" aria-live="polite"><h2>Feedback</h2><p className="muted">Grading…</p></section>;
  if (!result) return <section className="panel card"><h2>Feedback</h2><p className="muted">Draw your answer and check it — you'll get partial credit and a plain-language explanation here.</p></section>;
  const r = result, b = r.breakdown;
  const bars = [["Structures", b.nodes], ["Transformations", b.transformations], ["Mechanisms", b.mechanisms], ["Pathway", b.pathway]];
  return (
    <section className="panel card" aria-live="polite">
      <h2>Feedback</h2>
      <div className="fb-head">
        <ScoreDial value={r.overall_score} passed={r.passed} />
        <div>
          <div className="verdict" style={{ color: r.passed ? "var(--ok)" : "var(--warn)" }}>{r.passed ? "✓ Correct" : "Almost — let's refine"}</div>
          <span className={"badge " + (r.passed ? "badge-ok" : "badge-warn")}>{r.passed ? "PASS" : "REVIEW"}</span>
        </div>
      </div>
      <p className="summary">{r.summary}</p>
      <div className="bars">
        {bars.map(([l, v]) => (
          <div className="bar-row" key={l}>
            <span>{l}</span>
            <span className="bar-track"><span className="bar-fill" style={{ width: Math.round(v * 100) + "%" }} /></span>
            <span>{Math.round(v * 100)}%</span>
          </div>
        ))}
      </div>
      {r.hints.map((h, i) => (<div className="callout callout-hint" key={i}><span aria-hidden="true">➜</span><span>{h}</span></div>))}
      {reveal && !r.passed && <RevealPanel problemId={reveal.problemId} product={reveal.product} />}
      <details className="fb-details">
        <summary>Show step-by-step details</summary>
        {r.nodes.map((n) => (
          <div className="fb-item" key={n.node_id}>
            <div className="fb-item-head">{n.node_id}<span className={"pill " + n.status}>{n.status.replace("_", " ")}</span></div>
            {n.smiles && <div className="fb-smiles">{n.smiles}{n.iupac_name ? " · " + n.iupac_name : ""}</div>}
            {n.message && <div className="fb-line">{n.message}</div>}
          </div>
        ))}
        {r.edges.map((e) => (
          <div className="fb-item" key={e.edge_id}>
            <div className="fb-item-head">
              {e.source} → {e.target}
              <span className={"pill " + (e.transformation_plausible ? "correct" : "wrong")}>transform</span>
              {e.mechanism_stated && <span className={"pill " + (e.mechanism_consistent ? "correct" : "wrong")}>{e.mechanism_stated}</span>}
              {!e.conservation_ok && <span className="pill unbalanced">unbalanced</span>}
            </div>
            {e.changes.length > 0 && <div className="fb-line fb-smiles">{e.changes.join(" · ")}</div>}
            {e.errors.map((x, i) => <div className="fb-line fb-err" key={"e" + i}>✗ {x}</div>)}
            {e.warnings.map((x, i) => <div className="fb-line fb-warn" key={"w" + i}>⚠ {x}</div>)}
            {e.hints.map((x, i) => <div className="fb-line fb-hint" key={"h" + i}>➜ {x}</div>)}
          </div>
        ))}
      </details>
    </section>
  );
}

// ---- practice mode ----
function PracticeView({ openEditor, setResult, setGrading, setReveal }) {
  const [problems, setProblems] = useState([]);
  const [byId, setById] = useState({});
  const [cur, setCur] = useState(null);
  const [product, setProduct] = useState(null);
  const [mech, setMech] = useState("");

  useEffect(() => {
    api("/problems").then((list) => {
      setProblems(list);
      const m = {}; list.forEach((p) => (m[p.id] = p)); setById(m);
      if (list.length) setCur(list[0].id);
    }).catch(() => {});
  }, []);
  useEffect(() => { setProduct(null); setMech(""); setResult(null); setReveal(null); }, [cur]);

  const p = cur ? byId[cur] : null;
  const check = async () => {
    setGrading(true);
    try {
      setResult(await api(`/problems/${cur}/grade`, { method: "POST", body: JSON.stringify({ product_smiles: product, mechanism_type: mech }) }));
      setReveal({ problemId: cur, product });
    } catch (_) { setResult(null); }
    setGrading(false);
  };
  if (!p) return <section className="panel card"><h2>Practice</h2><p className="muted">Loading problems…</p></section>;
  const cond = [p.reagents.join(", "), p.conditions].filter(Boolean).join(" · ");
  const draw = () => openEditor("Draw your product", (s) => setProduct(s));

  return (
    <section className="panel card">
      <label className="field-label" htmlFor="prob">Problem (SN1 · SN2 · E1 · E2)</label>
      <select id="prob" className="select problem-select" value={cur} onChange={(e) => setCur(e.target.value)}>
        {problems.map((pr) => <option key={pr.id} value={pr.id}>{pr.title}</option>)}
      </select>
      <p className="prompt">{p.prompt}</p>
      <div className="rxn">
        <div className="rxn-box"><div className="rxn-cap">starting material</div><Depiction smiles={p.start_smiles} /></div>
        <div className="rxn-mid"><div className="rxn-arrow" aria-hidden="true">→</div>{cond || "—"}</div>
        <div className="rxn-box">
          <div className="rxn-cap">your product</div>
          <div className="product-slot">
            {product
              ? <><Depiction smiles={product} /><div className="product-smiles">{product}</div><button className="btn btn-ghost" onClick={draw}>Redraw</button></>
              : <button className="btn btn-primary" onClick={draw}>✎ Draw product</button>}
          </div>
        </div>
      </div>
      <label className="field-label">Mechanism</label>
      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", marginBottom: "var(--space-4)" }} role="group" aria-label="Mechanism">
        {["SN1", "SN2", "E1", "E2"].map((m) => (
          <button key={m} className="btn mech-btn" aria-pressed={mech === m} onClick={() => setMech(m)}>{m}</button>
        ))}
      </div>
      <button className="btn btn-primary check" disabled={!(product && mech)} onClick={check}>Check work</button>
      {p.hint && <details className="hint-box"><summary>Need a hint?</summary>{p.hint}</details>}
    </section>
  );
}

// ---- free build mode ----
const emptyGraphs = () => ({ reference: { nodes: [], edges: [], seq: 0 }, attempt: { nodes: [], edges: [], seq: 0 } });

function layout(g) {
  const depth = {}, pos = {};
  g.nodes.forEach((n) => (depth[n.id] = 0));
  for (let i = 0; i < g.nodes.length; i++) {
    let changed = false;
    g.edges.forEach((e) => { const d = (depth[e.source] ?? 0) + 1; if (d > (depth[e.target] ?? 0)) { depth[e.target] = d; changed = true; } });
    if (!changed) break;
  }
  const row = {};
  g.nodes.forEach((n) => { const d = depth[n.id] || 0, ro = row[d] || 0; row[d] = ro + 1; pos[n.id] = { x: 20 + d * 236, y: 24 + ro * 128, w: 200, h: 104 }; });
  return pos;
}

function GraphCanvas({ g }) {
  const pos = layout(g);
  let maxX = 320, maxY = 300;
  g.nodes.forEach((n) => { const p = pos[n.id]; maxX = Math.max(maxX, p.x + p.w + 24); maxY = Math.max(maxY, p.y + p.h + 24); });
  return (
    <div className="graph-wrap" style={{ height: maxY }}>
      {g.nodes.length === 0 && <div className="graph-empty">Add a structure to start building the mechanism.</div>}
      <svg width={maxX} height={maxY} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
        <defs><marker id="arr" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#94a3b8" /></marker></defs>
        {g.edges.map((e) => {
          const s = pos[e.source], t = pos[e.target]; if (!s || !t) return null;
          const x1 = s.x + s.w, y1 = s.y + s.h / 2, x2 = t.x, y2 = t.y + t.h / 2, mx = (x1 + x2) / 2;
          return (
            <g key={e.id}>
              <path d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2 - 8},${y2}`} fill="none" stroke="#94a3b8" strokeWidth="1.6" markerEnd="url(#arr)" />
              <text x={mx} y={(y1 + y2) / 2 - 6} textAnchor="middle" fontSize="10.5" fill="#6b7280">{[e.mechanism_type, (e.reagents || []).join(", ")].filter(Boolean).join(" · ").slice(0, 40)}</text>
            </g>
          );
        })}
      </svg>
      {g.nodes.map((n) => {
        const p = pos[n.id];
        return (
          <div className="gnode" key={n.id} style={{ left: p.x, top: p.y }}>
            <span className="gnode-id">{n.id}</span>
            <Depiction smiles={n.smiles} w={184} h={70} />
            <div className="gnode-meta">{[n.formula, n.name].filter(Boolean).join(" · ")}</div>
          </div>
        );
      })}
    </div>
  );
}

function FreeBuildView({ openEditor, setResult, setGrading, setReveal }) {
  const [graphs, setGraphs] = useState(emptyGraphs);
  const [active, setActive] = useState("reference");
  const [mechs, setMechs] = useState([]);
  const [src, setSrc] = useState(""); const [tgt, setTgt] = useState(""); const [reag, setReag] = useState(""); const [emech, setEmech] = useState("");
  useEffect(() => { api("/mechanisms").then(setMechs).catch(() => {}); }, []);
  const g = graphs[active];
  const update = (mut) => setGraphs((prev) => { const ng = { ...prev, [active]: { ...prev[active] } }; mut(ng[active]); return ng; });

  const drawNode = () => openEditor("Draw a structure", async (smiles) => {
    let info = null; try { info = await api("/structure/canonical", { method: "POST", body: JSON.stringify({ smiles, with_name: true }) }); } catch (_) {}
    update((gr) => { const id = "n" + ++gr.seq; gr.nodes = [...gr.nodes, { id, smiles: info ? info.canonical_smiles : smiles, formula: info ? info.formula : "", name: info ? info.iupac_name : null }]; });
  });
  const addEdge = () => {
    if (!src || !tgt || src === tgt) return;
    update((gr) => { gr.edges = [...gr.edges, { id: "e" + ++gr.seq, source: src, target: tgt, reagents: reag.split(",").map((s) => s.trim()).filter(Boolean), mechanism_type: emech || null }]; });
    setReag("");
  };
  const clear = () => setGraphs((prev) => ({ ...prev, [active]: { nodes: [], edges: [], seq: 0 } }));
  const grade = async () => {
    setGrading(true); setReveal(null);
    try {
      const pay = (gr) => ({ nodes: gr.nodes.map((n) => ({ id: n.id, smiles: n.smiles, label: n.name })), edges: gr.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, reagents: e.reagents, mechanism_type: e.mechanism_type || null })) });
      setResult(await api("/grade", { method: "POST", body: JSON.stringify({ reference: pay(graphs.reference), attempt: pay(graphs.attempt) }) }));
    } catch (_) { setResult(null); }
    setGrading(false);
  };
  const opts = g.nodes.map((n) => <option key={n.id} value={n.id}>{n.id}: {n.smiles.slice(0, 16)}</option>);

  return (
    <section className="panel card">
      <div className="tabs" role="tablist" aria-label="Graph">
        <button className="tab" role="tab" aria-selected={active === "reference"} onClick={() => setActive("reference")}>Reference answer</button>
        <button className="tab" role="tab" aria-selected={active === "attempt"} onClick={() => setActive("attempt")}>Student attempt</button>
      </div>
      <GraphCanvas g={g} />
      <div className="controls">
        <div className="row">
          <button className="btn btn-primary" onClick={drawNode}>✎ Draw structure</button>
          <span className="muted">then connect steps below</span>
        </div>
        <div className="row">
          <select className="select" aria-label="From" value={src} onChange={(e) => setSrc(e.target.value)}><option value="">from…</option>{opts}</select>
          <span aria-hidden="true">→</span>
          <select className="select" aria-label="To" value={tgt} onChange={(e) => setTgt(e.target.value)}><option value="">to…</option>{opts}</select>
          <input className="input grow" placeholder="reagents, e.g. NaOH, heat" value={reag} onChange={(e) => setReag(e.target.value)} />
          <select className="select" aria-label="Mechanism" value={emech} onChange={(e) => setEmech(e.target.value)}><option value="">mechanism?</option>{mechs.map((m) => <option key={m.mechanism_type} value={m.mechanism_type}>{m.mechanism_type}</option>)}</select>
          <button className="btn" onClick={addEdge}>Add step</button>
        </div>
        <div className="actions">
          <button className="btn btn-ghost btn-danger" onClick={clear}>Clear this graph</button>
          <button className="btn btn-primary" onClick={grade}>Grade attempt vs reference</button>
        </div>
      </div>
    </section>
  );
}

// ---- app shell ----
function TopBar({ mode, setMode }) {
  return (
    <header className="topbar">
      <div className="brand"><span className="dot" aria-hidden="true" /> Reaction Grader</div>
      <div className="topbar-spacer" />
      <div className="seg" role="group" aria-label="Mode">
        <button className="seg-btn" aria-pressed={mode === "practice"} onClick={() => setMode("practice")}>Practice</button>
        <button className="seg-btn" aria-pressed={mode === "build"} onClick={() => setMode("build")}>Free build</button>
      </div>
      <a className="btn btn-ghost" href="builder.html" style={{ marginLeft: "var(--space-3)" }}>✎ Builder</a>
    </header>
  );
}

function App() {
  const [mode, setMode] = useState("practice");
  const [result, setResult] = useState(null);
  const [grading, setGrading] = useState(false);
  const [editor, setEditor] = useState(null);
  const [reveal, setReveal] = useState(null);
  const openEditor = (title, onAccept) => setEditor({ title, onAccept });
  const switchMode = (m) => { setMode(m); setResult(null); setReveal(null); };
  return (
    <div className="app">
      <TopBar mode={mode} setMode={switchMode} />
      <main className="app-main">
        <div>
          {mode === "practice"
            ? <PracticeView openEditor={openEditor} setResult={setResult} setGrading={setGrading} setReveal={setReveal} />
            : <FreeBuildView openEditor={openEditor} setResult={setResult} setGrading={setGrading} setReveal={setReveal} />}
        </div>
        <Feedback result={result} grading={grading} reveal={reveal} />
      </main>
      {editor && <EditorModal title={editor.title} onCancel={() => setEditor(null)} onUse={(s) => { const cb = editor.onAccept; setEditor(null); cb(s); }} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
