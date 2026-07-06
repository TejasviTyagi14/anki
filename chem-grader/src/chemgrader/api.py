"""FastAPI surface for the mechanism grader.

Endpoints
---------
* ``POST /reference``            -- store a reference mechanism graph -> ``{id}``
* ``GET  /graph/{id}``           -- fetch a stored graph (enriched)
* ``POST /grade``                -- grade an attempt vs a reference -> GradeResult
* ``POST /structure/canonical``  -- SMILES -> identity + properties (utility)
* ``POST /structure/from-input`` -- drawing/editor payload -> SMILES (mock stubs)
* ``GET  /mechanisms``           -- list the mechanism rule library

Run with:  ``uvicorn chemgrader.api:app --reload``  (PYTHONPATH=src)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import flashcards as flashcards_module
from . import llm_grader
from . import problems as problems_module
from .depiction import render_svg
from .feedback import GradeResult
from .grader import Grader, GraderConfig
from .mechanisms import MechanismRuleLibrary
from .models import MoleculeNode, ReactionGraph
from .name_resolver import MockNameResolver
from .store import GraphStore
from .transformation import structural_diff
from .structure_input import (
    MockOcrStructureInput,
    MolblockInput,
    SmilesPassthroughInput,
    StructureInputError,
)
from .structure_service import StructureError, StructureService

# ---- request/response models ---------------------------------------- #


class CanonicalRequest(BaseModel):
    smiles: str
    with_name: bool = True


class CanonicalResponse(BaseModel):
    canonical_smiles: str
    inchi: str
    inchikey: str
    formula: str
    mol_weight: float
    functional_groups: list[str]
    iupac_name: Optional[str] = None


class FromInputRequest(BaseModel):
    source: str = Field(description="one of: smiles | molblock | ocr")
    payload: Any


class FromInputResponse(BaseModel):
    smiles: str


class ReferenceResponse(BaseModel):
    id: str


class GradeRequest(BaseModel):
    attempt: ReactionGraph
    reference: Optional[ReactionGraph] = None
    reference_id: Optional[str] = None
    config: Optional[GraderConfig] = None


class MechanismInfo(BaseModel):
    mechanism_type: str
    description: str
    reagent_hints: list[str]


class ProblemInfo(BaseModel):
    id: str
    mechanism: str
    title: str
    prompt: str
    start_smiles: str
    reagents: list[str]
    conditions: Optional[str] = None
    hint: Optional[str] = None


class ProblemAttempt(BaseModel):
    product_smiles: str
    mechanism_type: Optional[str] = None


class SvgRequest(BaseModel):
    smiles: str
    highlight_atoms: list[int] = Field(default_factory=list)
    highlight_bonds: list[list[int]] = Field(default_factory=list)
    width: int = 280
    height: int = 200


class DiffRequest(BaseModel):
    a: str
    b: str


class FlashcardGradeRequest(BaseModel):
    """A hand-drawn answer to grade with the vision model.

    Either ``problem_id`` (a card from the bank) or ``statement`` (a custom
    question) must be supplied. ``payload`` is the machine-readable molecular
    graph from the frontend's ``buildSubmission``; ``image_png_base64`` is the
    canvas snapshot (no ``data:`` prefix).
    """

    problem_id: Optional[str] = None
    statement: Optional[str] = None
    image_png_base64: str
    payload: dict = Field(default_factory=dict)
    hint: bool = False
    freehand: bool = False


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency).

    Reads ``KEY=value`` or ``export KEY=value`` lines (blank lines and ``#``
    comments ignored) into the process environment. A variable already set in
    the real environment always wins, so an explicit ``export`` still overrides
    the file.
    """
    try:
        if not path.is_file():
            return
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, sep, val = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)
    except OSError:
        pass


class MechGradeRequest(BaseModel):
    # A MechGrader structured mechanism: {"steps": [{reactants, arrows, products}]}
    submission: dict
    reference: dict
    pass_threshold: int = 70


def create_app() -> FastAPI:
    # Load chem-grader/.env (gitignored) so the OpenAI key/config can live in a
    # file instead of being exported into every shell.
    _load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    app = FastAPI(
        title="Reaction Mechanism Grader",
        version="0.1.0",
        description="Grade multi-step organic reaction mechanism graphs (RDKit + NetworkX).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    service = StructureService()
    library = MechanismRuleLibrary()
    name_resolver = MockNameResolver()
    grader = Grader(service=service, library=library, name_resolver=name_resolver)
    store = GraphStore()

    inputs = {
        "smiles": SmilesPassthroughInput(),
        "molblock": MolblockInput(),
        "ocr": MockOcrStructureInput(),
    }

    @app.get("/api")
    def api_info() -> dict:
        return {
            "name": "Reaction Mechanism Grader",
            "endpoints": [
                "POST /reference",
                "GET /graph/{id}",
                "POST /grade",
                "POST /mech/grade",
                "POST /structure/canonical",
                "POST /structure/from-input",
                "GET /mechanisms",
                "GET /flashcards",
                "GET /flashcards/{id}",
                "POST /flashcards/grade",
            ],
            "apps": {"mechgrader_editor": "/", "legacy_chemgrader": "/app/"},
        }

    @app.post("/structure/canonical", response_model=CanonicalResponse)
    def canonical(req: CanonicalRequest) -> CanonicalResponse:
        try:
            ident = service.identity(req.smiles)
        except StructureError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        name = None
        if req.with_name:
            try:
                name = name_resolver.to_iupac(ident.canonical_smiles)
            except Exception:
                name = None
        return CanonicalResponse(
            canonical_smiles=ident.canonical_smiles,
            inchi=ident.inchi,
            inchikey=ident.inchikey,
            formula=ident.formula,
            mol_weight=ident.mol_weight,
            functional_groups=ident.functional_groups,
            iupac_name=name,
        )

    @app.post("/structure/from-input", response_model=FromInputResponse)
    def from_input(req: FromInputRequest) -> FromInputResponse:
        handler = inputs.get(req.source)
        if handler is None:
            raise HTTPException(
                status_code=400,
                detail=f"unknown source {req.source!r}; expected one of {list(inputs)}",
            )
        try:
            return FromInputResponse(smiles=handler.to_smiles(req.payload))
        except StructureInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/reference", response_model=ReferenceResponse)
    def submit_reference(graph: ReactionGraph) -> ReferenceResponse:
        for node in graph.nodes:
            service.enrich(node, name_resolver)
        return ReferenceResponse(id=store.put(graph))

    @app.get("/graph/{graph_id}", response_model=ReactionGraph)
    def get_graph(graph_id: str) -> ReactionGraph:
        graph = store.get(graph_id)
        if graph is None:
            raise HTTPException(status_code=404, detail=f"no graph {graph_id!r}")
        return graph

    @app.post("/grade", response_model=GradeResult)
    def grade(req: GradeRequest) -> GradeResult:
        reference = req.reference
        if reference is None and req.reference_id:
            reference = store.get(req.reference_id)
        if reference is None:
            raise HTTPException(
                status_code=400,
                detail="provide either 'reference' or a valid 'reference_id'",
            )
        return grader.grade(reference, req.attempt, req.config)

    @app.post("/mech/grade")
    def mech_grade(req: MechGradeRequest) -> dict:
        """Grade a MechGrader structured mechanism (steps -> reactants/arrows/
        products) against a reference, via the MechGrader deterministic grader
        (RDKit). This is what the web editor's Submit calls for real grades."""
        import pathlib
        import sys

        repo_root = pathlib.Path(__file__).resolve().parents[3]  # .../anki
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from mechgrader.grading.deterministic import grade_mechanism
        except Exception as exc:  # mechgrader not importable
            raise HTTPException(status_code=500, detail=f"grader unavailable: {exc}")
        return grade_mechanism(
            req.submission, req.reference, pass_threshold=req.pass_threshold
        )

    @app.get("/mechanisms", response_model=list[MechanismInfo])
    def mechanisms() -> list[MechanismInfo]:
        return [
            MechanismInfo(
                mechanism_type=t.mechanism_type.value,
                description=t.description,
                reagent_hints=t.reagent_hints,
            )
            for t in library.all()
        ]

    @app.get("/problems", response_model=list[ProblemInfo])
    def list_problems() -> list[ProblemInfo]:
        return [ProblemInfo(**p.public()) for p in problems_module.PROBLEMS]

    @app.post("/problems/{problem_id}/grade", response_model=GradeResult)
    def grade_problem(problem_id: str, attempt: ProblemAttempt) -> GradeResult:
        problem = problems_module.get_problem(problem_id)
        if problem is None:
            raise HTTPException(status_code=404, detail=f"no problem {problem_id!r}")
        return problems_module.grade_problem(
            problem, attempt.product_smiles, attempt.mechanism_type, grader
        )

    @app.get("/problems/{problem_id}/answer")
    def problem_answer(problem_id: str) -> dict:
        """Reveal the expected answer -- used only after the student asks for it."""
        problem = problems_module.get_problem(problem_id)
        if problem is None:
            raise HTTPException(status_code=404, detail=f"no problem {problem_id!r}")
        return {"products": problem.products, "mechanism": problem.mechanism}

    # ---- flashcards: draw-by-hand answers graded by a vision model --------- #

    @app.get("/flashcards")
    def list_flashcards() -> list[dict]:
        """The card fronts only -- answer keys never leave the server."""
        return [c.public() for c in flashcards_module.FLASHCARDS]

    @app.get("/flashcards/{card_id}")
    def get_flashcard(card_id: str) -> dict:
        card = flashcards_module.get_flashcard(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"no flashcard {card_id!r}")
        return card.public()

    @app.post("/flashcards/grade")
    def grade_flashcard(req: FlashcardGradeRequest) -> dict:
        if not req.image_png_base64:
            raise HTTPException(status_code=400, detail="missing image_png_base64")

        statement = (req.statement or "").strip()
        reference_answer: Optional[str] = None
        expected: list[str] = []
        stereo = False
        if req.problem_id and req.problem_id != "custom":
            card = flashcards_module.get_flashcard(req.problem_id)
            if card is None:
                raise HTTPException(status_code=404, detail=f"no flashcard {req.problem_id!r}")
            statement = card.statement
            reference_answer = card.reference_answer
            expected = card.expected_smiles
            stereo = card.stereo_required
        if not statement:
            raise HTTPException(status_code=400, detail="empty problem statement")

        try:
            return llm_grader.grade_drawing(
                statement=statement,
                reference_answer=reference_answer,
                expected_smiles=expected,
                stereo_required=stereo,
                image_png_base64=req.image_png_base64,
                payload=req.payload or {},
                hint_mode=bool(req.hint),
                service=service,
                freehand=bool(req.freehand),
            )
        except llm_grader.GraderConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except llm_grader.GraderCallError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/flashcards.html")
    def flashcards_page() -> RedirectResponse:
        """Convenience redirect to the static page's real URL under /app/."""
        return RedirectResponse(url="/app/flashcards.html")

    @app.post("/structure/svg")
    def structure_svg(req: SvgRequest) -> Response:
        try:
            svg = render_svg(req.smiles, req.highlight_atoms, req.highlight_bonds, req.width, req.height)
        except StructureError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=svg, media_type="image/svg+xml")

    @app.post("/structure/diff")
    def structure_diff(req: DiffRequest) -> dict:
        try:
            return structural_diff(req.a, req.b)
        except StructureError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The legacy chem-grader prototype frontend stays at /app/ for reference.
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    # Serve the CURRENT MechGrader editor (the shared web/mechgrader bundle,
    # same one desktop/iOS use) at the root, on the same origin as the grader.
    # So http://localhost:8000/ is the new editor and its Submit reaches
    # /mech/grade with no CORS. Mounted last so the API routes above win.
    editor_dir = Path(__file__).resolve().parents[3] / "web" / "mechgrader"
    if editor_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(editor_dir), html=True), name="editor")

    return app


app = create_app()
