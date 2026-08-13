from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .agents import PruefPilot
from .document_ai import inspect_document
from .models import CaseQuestionRequest, CaseQuestionResponse
from .retrieval import search_sources

app = FastAPI(title="PrüfPilot Document AI", version="5.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pilot = PruefPilot()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "5.1.0"}


@app.get("/api/v5/cases")
def v5_cases() -> list[dict[str, Any]]:
    return [item.model_dump() for item in pilot.v5_cases()]


@app.get("/api/v5/cases/{case_id}")
def v5_case(case_id: str) -> dict[str, Any]:
    case = pilot.v5_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case_not_found")
    return case.model_dump()


@app.post("/api/v5/cases/{case_id}/ask", response_model=CaseQuestionResponse)
def v5_ask(case_id: str, body: CaseQuestionRequest) -> CaseQuestionResponse:
    try:
        return pilot.answer_v5_question(case_id, body.question)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case_not_found") from exc


@app.get("/api/cases")
def cases() -> list[dict[str, Any]]:
    return [item.model_dump() for item in pilot.queue()]


@app.get("/api/intake")
def intake() -> dict[str, Any]:
    return pilot.intake().model_dump()


@app.get("/api/phase-one-map")
def phase_one_map() -> list[dict[str, Any]]:
    return [item.model_dump() for item in pilot.phase_one_map()]


@app.get("/api/retrieval")
def retrieval(q: str, limit: int = 5) -> dict[str, Any]:
    return {"query": q, "results": [item.model_dump() for item in search_sources(q, limit=limit)]}


@app.post("/api/document/inspect")
async def document_inspect(
    file: UploadFile = File(...),
    domain: str = Form(default="generic"),
) -> dict[str, Any]:
    raw = await file.read()
    try:
        report = inspect_document(raw, filename=file.filename or "upload.pdf", domain=domain)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.model_dump()


@app.get("/api/aconium/fit")
def aconium_fit() -> dict[str, list[str]]:
    return {
        "company_understanding": [
            "aconium supports public-sector implementation, funding and complex project administration.",
            "The product must fit real reviewer workflows and existing specialist systems.",
            "Traceability, data governance and human responsibility matter as much as model quality.",
        ],
        "phase_one": [
            "One domain and one reviewer workflow first.",
            "FastAPI and typed tools as stable contracts.",
            "Grounded RAG, bounded agents, MCP and evaluation gates.",
            "Measure reviewer correction rate before scaling models or domains.",
        ],
        "production_next": [
            "SSO/RBAC and tenant isolation",
            "durable Postgres/object storage and asynchronous processing",
            "DMS/funding-system adapters",
            "labelled evaluation corpus and provider benchmark",
            "monitoring, SLOs, retention and deletion policies",
        ],
    }


# Vercel serves public/** directly. Local/Docker runs mount the same assets when present.
# The repository's current V5.1 frontend lives under frontend/v5.1, so API-only tests
# and installs must not fail just because a legacy root public/ directory is absent.
if not os.getenv("VERCEL"):
    public_dir = Path(__file__).resolve().parents[1] / "public"
    if public_dir.is_dir():
        app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
