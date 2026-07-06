(() => {
  const { useState } = React;
  const MoleculeEditor = window.MoleculeEditor;
  function BuilderPage() {
    const [payload, setPayload] = useState(null);
    const [showJson, setShowJson] = useState(false);
    const [copied, setCopied] = useState(false);
    const molecule = payload ? payload.molecule : { atoms: [], bonds: [] };
    const jsonStr = JSON.stringify(molecule, null, 2);
    const readout = payload && payload.smiles ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("b", null, payload.smiles), " \xB7 " + payload.formula, payload.name ? " \xB7 " + payload.name : "") : payload && payload.error ? /* @__PURE__ */ React.createElement("span", { className: "mb-err" }, "\u26A0 ", payload.error) : /* @__PURE__ */ React.createElement("span", { className: "mb-muted" }, "Draw a skeletal structure\u2026");
    return /* @__PURE__ */ React.createElement("div", { className: "mb-app" }, /* @__PURE__ */ React.createElement("header", { className: "mb-head" }, /* @__PURE__ */ React.createElement("div", { className: "mb-brand" }, /* @__PURE__ */ React.createElement("span", { className: "mb-dot" }), " Molecule Builder"), /* @__PURE__ */ React.createElement("div", { className: "mb-readout" }, readout), /* @__PURE__ */ React.createElement("div", { className: "mb-head-actions" }, /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost", onClick: () => setShowJson((v) => !v) }, showJson ? "Hide JSON" : "JSON"), /* @__PURE__ */ React.createElement("a", { className: "btn btn-ghost", href: "./" }, "\u2190 Grader"))), /* @__PURE__ */ React.createElement("div", { className: "mb-stage" }, /* @__PURE__ */ React.createElement(MoleculeEditor, { onMolecule: (p) => {
      setPayload(p);
      setCopied(false);
    } })), showJson && /* @__PURE__ */ React.createElement("div", { className: "mb-json card" }, /* @__PURE__ */ React.createElement("div", { className: "mb-json-head" }, /* @__PURE__ */ React.createElement("span", null, "molecule.json"), /* @__PURE__ */ React.createElement("button", { className: "btn btn-ghost", onClick: () => {
      navigator.clipboard.writeText(jsonStr);
      setCopied(true);
    } }, copied ? "Copied" : "Copy")), /* @__PURE__ */ React.createElement("pre", null, jsonStr)));
  }
  ReactDOM.createRoot(document.getElementById("root")).render(/* @__PURE__ */ React.createElement(BuilderPage, null));
})();
