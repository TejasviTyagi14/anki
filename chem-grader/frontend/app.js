(() => {
  const { useState, useEffect, useRef } = React;
  const MoleculeEditor = window.MoleculeEditor;
  const API = location.origin;
  async function api(path, opts) {
    const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) {
      let d = r.statusText;
      try {
        d = (await r.json()).detail || d;
      } catch (_) {
      }
      throw new Error(d);
    }
    return r.json();
  }
  function Depiction({ smiles, w = 200, h = 110 }) {
    const ref = useRef(null);
    useEffect(() => {
      const c = ref.current;
      if (!c) return;
      const ctx = c.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, c.width, c.height);
      if (!smiles || typeof SmilesDrawer === "undefined") return;
      try {
        const d = new SmilesDrawer.Drawer({ width: w, height: h, bondThickness: 1.1 });
        SmilesDrawer.parse(smiles, (t) => d.draw(t, c, "light", false), () => {
        });
      } catch (_) {
      }
    }, [smiles, w, h]);
    return /* @__PURE__ */ React.createElement("canvas", { ref, width: w, height: h, className: "depiction", role: "img", "aria-label": smiles ? "structure " + smiles : "structure" });
  }
  function SvgDepiction({ smiles, highlightAtoms = [], highlightBonds = [], w = 240, h = 170, label }) {
    const [svg, setSvg] = useState("");
    const key = JSON.stringify([smiles, highlightAtoms, highlightBonds, w, h]);
    useEffect(() => {
      let alive = true;
      if (!smiles) {
        setSvg("");
        return;
      }
      fetch(API + "/structure/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ smiles, highlight_atoms: highlightAtoms, highlight_bonds: highlightBonds, width: w, height: h }) }).then((r) => r.ok ? r.text() : "").then((t) => {
        if (alive) setSvg(t);
      }).catch(() => {
      });
      return () => {
        alive = false;
      };
    }, [key]);
    return /* @__PURE__ */ React.createElement("div", { className: "svg-depiction", role: "img", "aria-label": label || "structure " + (smiles || ""), dangerouslySetInnerHTML: { __html: svg } });
  }
  function RevealPanel({ problemId, product }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState("");
    const reveal = async () => {
      setLoading(true);
      setErr("");
      try {
        const ans = await api(`/problems/${problemId}/answer`);
        const expected = ans.products[0];
        const diff = await api("/structure/diff", { method: "POST", body: JSON.stringify({ a: product, b: expected }) });
        setData({ expected, diff });
      } catch (e) {
        setErr(e.message);
      }
      setLoading(false);
    };
    if (!data) {
      return /* @__PURE__ */ React.createElement("div", { className: "reveal" }, /* @__PURE__ */ React.createElement("button", { className: "btn", onClick: reveal, disabled: loading }, loading ? "Revealing\u2026" : "Reveal expected answer"), err && /* @__PURE__ */ React.createElement("span", { className: "fb-err", style: { marginLeft: 8 } }, err));
    }
    return /* @__PURE__ */ React.createElement("div", { className: "reveal" }, /* @__PURE__ */ React.createElement("div", { className: "reveal-grid" }, /* @__PURE__ */ React.createElement("div", { className: "reveal-box" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-cap" }, "your product"), /* @__PURE__ */ React.createElement(SvgDepiction, { smiles: product, highlightAtoms: data.diff.changed_atoms_a, highlightBonds: data.diff.changed_bonds_a, label: "your product, differences highlighted" })), /* @__PURE__ */ React.createElement("div", { className: "reveal-box" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-cap" }, "expected"), /* @__PURE__ */ React.createElement(SvgDepiction, { smiles: data.expected, highlightAtoms: data.diff.changed_atoms_b, highlightBonds: data.diff.changed_bonds_b, label: "expected product, differences highlighted" }))), /* @__PURE__ */ React.createElement("div", { className: "muted", style: { fontSize: "var(--text-xs)" } }, data.diff.same ? "Your structure matches the expected product \u2014 the issue is elsewhere (see the explanation above)." : "Highlighted atoms/bonds are where your structure differs from the expected one."));
  }
  function EditorModal({ title, onCancel, onUse }) {
    const [draft, setDraft] = useState(null);
    useEffect(() => {
      const onKey = (e) => {
        if (e.key === "Escape") onCancel();
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [onCancel]);
    return /* @__PURE__ */ React.createElement("div", { className: "modal-overlay", role: "dialog", "aria-modal": "true", "aria-label": title }, /* @__PURE__ */ React.createElement("div", { className: "modal card" }, /* @__PURE__ */ React.createElement("div", { className: "modal-head" }, /* @__PURE__ */ React.createElement("h3", null, title), /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost", "aria-label": "Close editor", onClick: onCancel }, "\u2715")), /* @__PURE__ */ React.createElement("div", { className: "modal-editor" }, /* @__PURE__ */ React.createElement(MoleculeEditor, { onMolecule: setDraft })), /* @__PURE__ */ React.createElement("div", { className: "modal-foot" }, /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost", onClick: onCancel }, "Cancel"), /* @__PURE__ */ React.createElement("button", { className: "btn btn-primary", disabled: !(draft && draft.smiles), onClick: () => onUse(draft.smiles) }, "Use structure"))));
  }
  function ScoreDial({ value, passed }) {
    const r = 32, circ = 2 * Math.PI * r, off = circ * (1 - Math.max(0, Math.min(1, value)));
    const col = passed ? "var(--ok)" : value >= 0.5 ? "var(--warn)" : "var(--err)";
    return /* @__PURE__ */ React.createElement("div", { className: "dial" }, /* @__PURE__ */ React.createElement("svg", { width: "76", height: "76", "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("circle", { cx: "38", cy: "38", r, fill: "none", stroke: "var(--surface-2)", strokeWidth: "8" }), /* @__PURE__ */ React.createElement("circle", { cx: "38", cy: "38", r, fill: "none", stroke: col, strokeWidth: "8", strokeLinecap: "round", strokeDasharray: circ, strokeDashoffset: off })), /* @__PURE__ */ React.createElement("div", { className: "dial-num" }, Math.round(value * 100), "%"));
  }
  function Feedback({ result, grading, reveal }) {
    if (grading) return /* @__PURE__ */ React.createElement("section", { className: "panel card", "aria-live": "polite" }, /* @__PURE__ */ React.createElement("h2", null, "Feedback"), /* @__PURE__ */ React.createElement("p", { className: "muted" }, "Grading\u2026"));
    if (!result) return /* @__PURE__ */ React.createElement("section", { className: "panel card" }, /* @__PURE__ */ React.createElement("h2", null, "Feedback"), /* @__PURE__ */ React.createElement("p", { className: "muted" }, "Draw your answer and check it \u2014 you'll get partial credit and a plain-language explanation here."));
    const r = result, b = r.breakdown;
    const bars = [["Structures", b.nodes], ["Transformations", b.transformations], ["Mechanisms", b.mechanisms], ["Pathway", b.pathway]];
    return /* @__PURE__ */ React.createElement("section", { className: "panel card", "aria-live": "polite" }, /* @__PURE__ */ React.createElement("h2", null, "Feedback"), /* @__PURE__ */ React.createElement("div", { className: "fb-head" }, /* @__PURE__ */ React.createElement(ScoreDial, { value: r.overall_score, passed: r.passed }), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "verdict", style: { color: r.passed ? "var(--ok)" : "var(--warn)" } }, r.passed ? "\u2713 Correct" : "Almost \u2014 let's refine"), /* @__PURE__ */ React.createElement("span", { className: "badge " + (r.passed ? "badge-ok" : "badge-warn") }, r.passed ? "PASS" : "REVIEW"))), /* @__PURE__ */ React.createElement("p", { className: "summary" }, r.summary), /* @__PURE__ */ React.createElement("div", { className: "bars" }, bars.map(([l, v]) => /* @__PURE__ */ React.createElement("div", { className: "bar-row", key: l }, /* @__PURE__ */ React.createElement("span", null, l), /* @__PURE__ */ React.createElement("span", { className: "bar-track" }, /* @__PURE__ */ React.createElement("span", { className: "bar-fill", style: { width: Math.round(v * 100) + "%" } })), /* @__PURE__ */ React.createElement("span", null, Math.round(v * 100), "%")))), r.hints.map((h, i) => /* @__PURE__ */ React.createElement("div", { className: "callout callout-hint", key: i }, /* @__PURE__ */ React.createElement("span", { "aria-hidden": "true" }, "\u279C"), /* @__PURE__ */ React.createElement("span", null, h))), reveal && !r.passed && /* @__PURE__ */ React.createElement(RevealPanel, { problemId: reveal.problemId, product: reveal.product }), /* @__PURE__ */ React.createElement("details", { className: "fb-details" }, /* @__PURE__ */ React.createElement("summary", null, "Show step-by-step details"), r.nodes.map((n) => /* @__PURE__ */ React.createElement("div", { className: "fb-item", key: n.node_id }, /* @__PURE__ */ React.createElement("div", { className: "fb-item-head" }, n.node_id, /* @__PURE__ */ React.createElement("span", { className: "pill " + n.status }, n.status.replace("_", " "))), n.smiles && /* @__PURE__ */ React.createElement("div", { className: "fb-smiles" }, n.smiles, n.iupac_name ? " \xB7 " + n.iupac_name : ""), n.message && /* @__PURE__ */ React.createElement("div", { className: "fb-line" }, n.message))), r.edges.map((e) => /* @__PURE__ */ React.createElement("div", { className: "fb-item", key: e.edge_id }, /* @__PURE__ */ React.createElement("div", { className: "fb-item-head" }, e.source, " \u2192 ", e.target, /* @__PURE__ */ React.createElement("span", { className: "pill " + (e.transformation_plausible ? "correct" : "wrong") }, "transform"), e.mechanism_stated && /* @__PURE__ */ React.createElement("span", { className: "pill " + (e.mechanism_consistent ? "correct" : "wrong") }, e.mechanism_stated), !e.conservation_ok && /* @__PURE__ */ React.createElement("span", { className: "pill unbalanced" }, "unbalanced")), e.changes.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "fb-line fb-smiles" }, e.changes.join(" \xB7 ")), e.errors.map((x, i) => /* @__PURE__ */ React.createElement("div", { className: "fb-line fb-err", key: "e" + i }, "\u2717 ", x)), e.warnings.map((x, i) => /* @__PURE__ */ React.createElement("div", { className: "fb-line fb-warn", key: "w" + i }, "\u26A0 ", x)), e.hints.map((x, i) => /* @__PURE__ */ React.createElement("div", { className: "fb-line fb-hint", key: "h" + i }, "\u279C ", x))))));
  }
  function PracticeView({ openEditor, setResult, setGrading, setReveal }) {
    const [problems, setProblems] = useState([]);
    const [byId, setById] = useState({});
    const [cur, setCur] = useState(null);
    const [product, setProduct] = useState(null);
    const [mech, setMech] = useState("");
    useEffect(() => {
      api("/problems").then((list) => {
        setProblems(list);
        const m = {};
        list.forEach((p2) => m[p2.id] = p2);
        setById(m);
        if (list.length) setCur(list[0].id);
      }).catch(() => {
      });
    }, []);
    useEffect(() => {
      setProduct(null);
      setMech("");
      setResult(null);
      setReveal(null);
    }, [cur]);
    const p = cur ? byId[cur] : null;
    const check = async () => {
      setGrading(true);
      try {
        setResult(await api(`/problems/${cur}/grade`, { method: "POST", body: JSON.stringify({ product_smiles: product, mechanism_type: mech }) }));
        setReveal({ problemId: cur, product });
      } catch (_) {
        setResult(null);
      }
      setGrading(false);
    };
    if (!p) return /* @__PURE__ */ React.createElement("section", { className: "panel card" }, /* @__PURE__ */ React.createElement("h2", null, "Practice"), /* @__PURE__ */ React.createElement("p", { className: "muted" }, "Loading problems\u2026"));
    const cond = [p.reagents.join(", "), p.conditions].filter(Boolean).join(" \xB7 ");
    const draw = () => openEditor("Draw your product", (s) => setProduct(s));
    return /* @__PURE__ */ React.createElement("section", { className: "panel card" }, /* @__PURE__ */ React.createElement("label", { className: "field-label", htmlFor: "prob" }, "Problem (SN1 \xB7 SN2 \xB7 E1 \xB7 E2)"), /* @__PURE__ */ React.createElement("select", { id: "prob", className: "select problem-select", value: cur, onChange: (e) => setCur(e.target.value) }, problems.map((pr) => /* @__PURE__ */ React.createElement("option", { key: pr.id, value: pr.id }, pr.title))), /* @__PURE__ */ React.createElement("p", { className: "prompt" }, p.prompt), /* @__PURE__ */ React.createElement("div", { className: "rxn" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-box" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-cap" }, "starting material"), /* @__PURE__ */ React.createElement(Depiction, { smiles: p.start_smiles })), /* @__PURE__ */ React.createElement("div", { className: "rxn-mid" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-arrow", "aria-hidden": "true" }, "\u2192"), cond || "\u2014"), /* @__PURE__ */ React.createElement("div", { className: "rxn-box" }, /* @__PURE__ */ React.createElement("div", { className: "rxn-cap" }, "your product"), /* @__PURE__ */ React.createElement("div", { className: "product-slot" }, product ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement(Depiction, { smiles: product }), /* @__PURE__ */ React.createElement("div", { className: "product-smiles" }, product), /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost", onClick: draw }, "Redraw")) : /* @__PURE__ */ React.createElement("button", { className: "btn btn-primary", onClick: draw }, "\u270E Draw product")))), /* @__PURE__ */ React.createElement("label", { className: "field-label" }, "Mechanism"), /* @__PURE__ */ React.createElement("div", { style: { display: "flex", gap: "var(--space-2)", flexWrap: "wrap", marginBottom: "var(--space-4)" }, role: "group", "aria-label": "Mechanism" }, ["SN1", "SN2", "E1", "E2"].map((m) => /* @__PURE__ */ React.createElement("button", { key: m, className: "btn mech-btn", "aria-pressed": mech === m, onClick: () => setMech(m) }, m))), /* @__PURE__ */ React.createElement("button", { className: "btn btn-primary check", disabled: !(product && mech), onClick: check }, "Check work"), p.hint && /* @__PURE__ */ React.createElement("details", { className: "hint-box" }, /* @__PURE__ */ React.createElement("summary", null, "Need a hint?"), p.hint));
  }
  const emptyGraphs = () => ({ reference: { nodes: [], edges: [], seq: 0 }, attempt: { nodes: [], edges: [], seq: 0 } });
  function layout(g) {
    const depth = {}, pos = {};
    g.nodes.forEach((n) => depth[n.id] = 0);
    for (let i = 0; i < g.nodes.length; i++) {
      let changed = false;
      g.edges.forEach((e) => {
        var _a, _b;
        const d = ((_a = depth[e.source]) != null ? _a : 0) + 1;
        if (d > ((_b = depth[e.target]) != null ? _b : 0)) {
          depth[e.target] = d;
          changed = true;
        }
      });
      if (!changed) break;
    }
    const row = {};
    g.nodes.forEach((n) => {
      const d = depth[n.id] || 0, ro = row[d] || 0;
      row[d] = ro + 1;
      pos[n.id] = { x: 20 + d * 236, y: 24 + ro * 128, w: 200, h: 104 };
    });
    return pos;
  }
  function GraphCanvas({ g }) {
    const pos = layout(g);
    let maxX = 320, maxY = 300;
    g.nodes.forEach((n) => {
      const p = pos[n.id];
      maxX = Math.max(maxX, p.x + p.w + 24);
      maxY = Math.max(maxY, p.y + p.h + 24);
    });
    return /* @__PURE__ */ React.createElement("div", { className: "graph-wrap", style: { height: maxY } }, g.nodes.length === 0 && /* @__PURE__ */ React.createElement("div", { className: "graph-empty" }, "Add a structure to start building the mechanism."), /* @__PURE__ */ React.createElement("svg", { width: maxX, height: maxY, style: { position: "absolute", inset: 0 }, "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("defs", null, /* @__PURE__ */ React.createElement("marker", { id: "arr", markerWidth: "9", markerHeight: "9", refX: "7", refY: "3", orient: "auto" }, /* @__PURE__ */ React.createElement("path", { d: "M0,0 L7,3 L0,6 Z", fill: "#94a3b8" }))), g.edges.map((e) => {
      const s = pos[e.source], t = pos[e.target];
      if (!s || !t) return null;
      const x1 = s.x + s.w, y1 = s.y + s.h / 2, x2 = t.x, y2 = t.y + t.h / 2, mx = (x1 + x2) / 2;
      return /* @__PURE__ */ React.createElement("g", { key: e.id }, /* @__PURE__ */ React.createElement("path", { d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2 - 8},${y2}`, fill: "none", stroke: "#94a3b8", strokeWidth: "1.6", markerEnd: "url(#arr)" }), /* @__PURE__ */ React.createElement("text", { x: mx, y: (y1 + y2) / 2 - 6, textAnchor: "middle", fontSize: "10.5", fill: "#6b7280" }, [e.mechanism_type, (e.reagents || []).join(", ")].filter(Boolean).join(" \xB7 ").slice(0, 40)));
    })), g.nodes.map((n) => {
      const p = pos[n.id];
      return /* @__PURE__ */ React.createElement("div", { className: "gnode", key: n.id, style: { left: p.x, top: p.y } }, /* @__PURE__ */ React.createElement("span", { className: "gnode-id" }, n.id), /* @__PURE__ */ React.createElement(Depiction, { smiles: n.smiles, w: 184, h: 70 }), /* @__PURE__ */ React.createElement("div", { className: "gnode-meta" }, [n.formula, n.name].filter(Boolean).join(" \xB7 ")));
    }));
  }
  function FreeBuildView({ openEditor, setResult, setGrading, setReveal }) {
    const [graphs, setGraphs] = useState(emptyGraphs);
    const [active, setActive] = useState("reference");
    const [mechs, setMechs] = useState([]);
    const [src, setSrc] = useState("");
    const [tgt, setTgt] = useState("");
    const [reag, setReag] = useState("");
    const [emech, setEmech] = useState("");
    useEffect(() => {
      api("/mechanisms").then(setMechs).catch(() => {
      });
    }, []);
    const g = graphs[active];
    const update = (mut) => setGraphs((prev) => {
      const ng = { ...prev, [active]: { ...prev[active] } };
      mut(ng[active]);
      return ng;
    });
    const drawNode = () => openEditor("Draw a structure", async (smiles) => {
      let info = null;
      try {
        info = await api("/structure/canonical", { method: "POST", body: JSON.stringify({ smiles, with_name: true }) });
      } catch (_) {
      }
      update((gr) => {
        const id = "n" + ++gr.seq;
        gr.nodes = [...gr.nodes, { id, smiles: info ? info.canonical_smiles : smiles, formula: info ? info.formula : "", name: info ? info.iupac_name : null }];
      });
    });
    const addEdge = () => {
      if (!src || !tgt || src === tgt) return;
      update((gr) => {
        gr.edges = [...gr.edges, { id: "e" + ++gr.seq, source: src, target: tgt, reagents: reag.split(",").map((s) => s.trim()).filter(Boolean), mechanism_type: emech || null }];
      });
      setReag("");
    };
    const clear = () => setGraphs((prev) => ({ ...prev, [active]: { nodes: [], edges: [], seq: 0 } }));
    const grade = async () => {
      setGrading(true);
      setReveal(null);
      try {
        const pay = (gr) => ({ nodes: gr.nodes.map((n) => ({ id: n.id, smiles: n.smiles, label: n.name })), edges: gr.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, reagents: e.reagents, mechanism_type: e.mechanism_type || null })) });
        setResult(await api("/grade", { method: "POST", body: JSON.stringify({ reference: pay(graphs.reference), attempt: pay(graphs.attempt) }) }));
      } catch (_) {
        setResult(null);
      }
      setGrading(false);
    };
    const opts = g.nodes.map((n) => /* @__PURE__ */ React.createElement("option", { key: n.id, value: n.id }, n.id, ": ", n.smiles.slice(0, 16)));
    return /* @__PURE__ */ React.createElement("section", { className: "panel card" }, /* @__PURE__ */ React.createElement("div", { className: "tabs", role: "tablist", "aria-label": "Graph" }, /* @__PURE__ */ React.createElement("button", { className: "tab", role: "tab", "aria-selected": active === "reference", onClick: () => setActive("reference") }, "Reference answer"), /* @__PURE__ */ React.createElement("button", { className: "tab", role: "tab", "aria-selected": active === "attempt", onClick: () => setActive("attempt") }, "Student attempt")), /* @__PURE__ */ React.createElement(GraphCanvas, { g }), /* @__PURE__ */ React.createElement("div", { className: "controls" }, /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("button", { className: "btn btn-primary", onClick: drawNode }, "\u270E Draw structure"), /* @__PURE__ */ React.createElement("span", { className: "muted" }, "then connect steps below")), /* @__PURE__ */ React.createElement("div", { className: "row" }, /* @__PURE__ */ React.createElement("select", { className: "select", "aria-label": "From", value: src, onChange: (e) => setSrc(e.target.value) }, /* @__PURE__ */ React.createElement("option", { value: "" }, "from\u2026"), opts), /* @__PURE__ */ React.createElement("span", { "aria-hidden": "true" }, "\u2192"), /* @__PURE__ */ React.createElement("select", { className: "select", "aria-label": "To", value: tgt, onChange: (e) => setTgt(e.target.value) }, /* @__PURE__ */ React.createElement("option", { value: "" }, "to\u2026"), opts), /* @__PURE__ */ React.createElement("input", { className: "input grow", placeholder: "reagents, e.g. NaOH, heat", value: reag, onChange: (e) => setReag(e.target.value) }), /* @__PURE__ */ React.createElement("select", { className: "select", "aria-label": "Mechanism", value: emech, onChange: (e) => setEmech(e.target.value) }, /* @__PURE__ */ React.createElement("option", { value: "" }, "mechanism?"), mechs.map((m) => /* @__PURE__ */ React.createElement("option", { key: m.mechanism_type, value: m.mechanism_type }, m.mechanism_type))), /* @__PURE__ */ React.createElement("button", { className: "btn", onClick: addEdge }, "Add step")), /* @__PURE__ */ React.createElement("div", { className: "actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost btn-danger", onClick: clear }, "Clear this graph"), /* @__PURE__ */ React.createElement("button", { className: "btn btn-primary", onClick: grade }, "Grade attempt vs reference"))));
  }
  function TopBar({ mode, setMode }) {
    return /* @__PURE__ */ React.createElement("header", { className: "topbar" }, /* @__PURE__ */ React.createElement("div", { className: "brand" }, /* @__PURE__ */ React.createElement("span", { className: "dot", "aria-hidden": "true" }), " Reaction Grader"), /* @__PURE__ */ React.createElement("div", { className: "topbar-spacer" }), /* @__PURE__ */ React.createElement("div", { className: "seg", role: "group", "aria-label": "Mode" }, /* @__PURE__ */ React.createElement("button", { className: "seg-btn", "aria-pressed": mode === "practice", onClick: () => setMode("practice") }, "Practice"), /* @__PURE__ */ React.createElement("button", { className: "seg-btn", "aria-pressed": mode === "build", onClick: () => setMode("build") }, "Free build")), /* @__PURE__ */ React.createElement("a", { className: "btn btn-ghost", href: "builder.html", style: { marginLeft: "var(--space-3)" } }, "\u270E Builder"));
  }
  function App() {
    const [mode, setMode] = useState("practice");
    const [result, setResult] = useState(null);
    const [grading, setGrading] = useState(false);
    const [editor, setEditor] = useState(null);
    const [reveal, setReveal] = useState(null);
    const openEditor = (title, onAccept) => setEditor({ title, onAccept });
    const switchMode = (m) => {
      setMode(m);
      setResult(null);
      setReveal(null);
    };
    return /* @__PURE__ */ React.createElement("div", { className: "app" }, /* @__PURE__ */ React.createElement(TopBar, { mode, setMode: switchMode }), /* @__PURE__ */ React.createElement("main", { className: "app-main" }, /* @__PURE__ */ React.createElement("div", null, mode === "practice" ? /* @__PURE__ */ React.createElement(PracticeView, { openEditor, setResult, setGrading, setReveal }) : /* @__PURE__ */ React.createElement(FreeBuildView, { openEditor, setResult, setGrading, setReveal })), /* @__PURE__ */ React.createElement(Feedback, { result, grading, reveal })), editor && /* @__PURE__ */ React.createElement(EditorModal, { title: editor.title, onCancel: () => setEditor(null), onUse: (s) => {
      const cb = editor.onAccept;
      setEditor(null);
      cb(s);
    } }));
  }
  ReactDOM.createRoot(document.getElementById("root")).render(/* @__PURE__ */ React.createElement(App, null));
})();
