/*
 * Standalone molecule-builder page. Thin wrapper around the shared
 * <MoleculeEditor> (editor.jsx) plus a header + JSON panel.
 */
const { useState } = React;
const MoleculeEditor = window.MoleculeEditor;

function BuilderPage() {
  const [payload, setPayload] = useState(null);
  const [showJson, setShowJson] = useState(false);
  const [copied, setCopied] = useState(false);

  const molecule = payload ? payload.molecule : { atoms: [], bonds: [] };
  const jsonStr = JSON.stringify(molecule, null, 2);
  const readout = payload && payload.smiles
    ? <><b>{payload.smiles}</b>{" · " + payload.formula}{payload.name ? " · " + payload.name : ""}</>
    : (payload && payload.error ? <span className="mb-err">⚠ {payload.error}</span> : <span className="mb-muted">Draw a skeletal structure…</span>);

  return (
    <div className="mb-app">
      <header className="mb-head">
        <div className="mb-brand"><span className="mb-dot" /> Molecule Builder</div>
        <div className="mb-readout">{readout}</div>
        <div className="mb-head-actions">
          <button className="btn btn-ghost" onClick={() => setShowJson((v) => !v)}>{showJson ? "Hide JSON" : "JSON"}</button>
          <a className="btn btn-ghost" href="./">← Grader</a>
        </div>
      </header>
      <div className="mb-stage"><MoleculeEditor onMolecule={(p) => { setPayload(p); setCopied(false); }} /></div>
      {showJson && (
        <div className="mb-json card">
          <div className="mb-json-head">
            <span>molecule.json</span>
            <button className="btn btn-ghost" onClick={() => { navigator.clipboard.writeText(jsonStr); setCopied(true); }}>{copied ? "Copied" : "Copy"}</button>
          </div>
          <pre>{jsonStr}</pre>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<BuilderPage />);
