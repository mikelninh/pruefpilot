from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .agents import PruefPilot
from .benchmark import run_benchmark
from .config import settings
from .document_ai import ingest_pdf
from .models import (
    AskRequest, AskResponse, BenchmarkReport, BenchmarkRunRequest, CaseSummary, CompletenessReport,
    EvidenceRequest, EvidenceResponse, FeedbackRequest, FeedbackResponse, QueueItem, ReviewMemo, UploadResult,
)
from .production import authenticate_api_key, fingerprint_actor, load_api_principals, production_readiness
from .storage import store
from .v5_cases import answer as v5_answer
from .v5_cases import evidence as v5_evidence
from .v5_cases import get_case as v5_get_case
from .v5_cases import list_cases as v5_list_cases
from .v5_cases import memo as v5_memo

app = FastAPI(
    title="PrüfPilot Document AI", version="5.3.0",
    description="Reusable public-sector case engine with grounded RAG, bounded agents, durable production storage options and human approval.",
    docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
)
production_mode = settings.app_env.strip().lower() == "production"
production_principals = load_api_principals()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins) if production_mode else list(settings.allowed_origins) + ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-api-key", "x-request-id", "x-tenant-id", "x-idempotency-key"],
)
pilot = PruefPilot()
PUBLIC_API_PATHS = {"/api/health", "/api/ready", "/api/docs", "/api/redoc", "/api/openapi.json"}


def _tenant_id(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    return principal.tenant_id if principal else "demo"


def _principal(request: Request):
    return getattr(request.state, "principal", None)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
    principal = None
    if production_mode and request.url.path.startswith("/api/") and request.url.path not in PUBLIC_API_PATHS:
        principal = authenticate_api_key(request.headers.get("x-api-key"), production_principals)
        if not principal:
            response = JSONResponse(status_code=401, content={"detail": "Production API authentication required"})
            response.headers["x-request-id"] = request_id
            response.headers["x-content-type-options"] = "nosniff"
            response.headers["x-frame-options"] = "DENY"
            return response
        claimed_tenant = request.headers.get("x-tenant-id")
        if claimed_tenant and claimed_tenant != principal.tenant_id:
            response = JSONResponse(status_code=403, content={"detail": "Cross-tenant request blocked"})
            response.headers["x-request-id"] = request_id
            response.headers["x-content-type-options"] = "nosniff"
            response.headers["x-frame-options"] = "DENY"
            return response
        request.state.principal = principal

    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    response.headers["x-pruefpilot-persistence"] = store.mode
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
    response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
    if principal:
        response.headers["x-pruefpilot-actor"] = fingerprint_actor(principal) or "authenticated"
    return response


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/index.html", status_code=307)


@app.get("/v5", include_in_schema=False)
def v5_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent / "v5.html")


@app.get("/api/v5/cases")
def v5_cases() -> list[dict]: return v5_list_cases()

@app.get("/api/v5/cases/{case_id}")
def v5_case(case_id: str) -> dict:
    case_data = v5_get_case(case_id)
    if not case_data: raise HTTPException(status_code=404, detail="Case not found")
    return case_data

@app.post("/api/v5/cases/{case_id}/ask")
def v5_ask(case_id: str, request: AskRequest) -> dict:
    result = v5_answer(case_id, request.question)
    if not result: raise HTTPException(status_code=404, detail="Case not found")
    return result

@app.post("/api/v5/cases/{case_id}/evidence")
def v5_check_evidence(case_id: str, request: EvidenceRequest) -> dict:
    result = v5_evidence(case_id, request.claim)
    if not result: raise HTTPException(status_code=404, detail="Case not found")
    return result

@app.post("/api/v5/cases/{case_id}/memo")
def v5_review_memo(case_id: str) -> dict:
    result = v5_memo(case_id)
    if not result: raise HTTPException(status_code=404, detail="Case not found")
    return result


def _readiness() -> dict:
    return production_readiness(
        app_env=settings.app_env, store_mode=store.mode, allowed_origins=settings.allowed_origins,
        tenant_scoped_persistence=store.tenant_scoped,
        object_store_durable=getattr(store, "object_store_durable", False), storage_health=store.health(),
    )


@app.get("/api/health")
def health() -> dict:
    readiness = _readiness()
    return {
        "status": "ok" if readiness["storage"].get("ok") else "degraded", "service": "pruefpilot",
        "version": app.version, "mode": settings.app_env, "persistence": store.mode,
        "readiness_stage": readiness["stage"], "storage": readiness["storage"],
        "llm_providers": {"openai": bool(settings.openai_api_key), "mistral": bool(settings.mistral_api_key), "local": bool(settings.local_model_url)},
    }

@app.get("/api/ready")
def ready() -> JSONResponse:
    readiness = _readiness()
    return JSONResponse(status_code=200 if readiness["ready"] else 503, content=readiness)

@app.get("/api/queue", response_model=list[QueueItem])
def queue() -> list[QueueItem]: return pilot.queue()

@app.get("/api/cases/{case_id}", response_model=CaseSummary)
def case(case_id: str) -> dict:
    if case_id != pilot.case["case_id"]: raise HTTPException(status_code=404, detail="Case not found")
    return pilot.case_summary()


@app.post("/api/upload", response_model=UploadResult)
async def upload_document(request: Request, file: UploadFile = File(...), case_id: str = Form("GF-2026-014")) -> UploadResult:
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF uploads are accepted")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes: raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_bytes} bytes")
    if not content.startswith(b"%PDF"): raise HTTPException(status_code=422, detail="The uploaded file is not a valid PDF")
    try:
        result = ingest_pdf(filename, content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"PDF extraction failed: {type(exc).__name__}") from exc

    tenant_id = _tenant_id(request)
    idem_key = request.headers.get("x-idempotency-key")
    if production_mode and not idem_key:
        raise HTTPException(status_code=400, detail="x-idempotency-key is required for production uploads")
    if idem_key:
        reservation = store.reserve_idempotency(tenant_id=tenant_id, operation="upload", key=idem_key)
        if not reservation["created"]:
            if reservation["response"]:
                return UploadResult.model_validate(reservation["response"])
            raise HTTPException(status_code=409, detail="Upload with this idempotency key is already in progress")

    store.save_upload(case_id, result.model_dump(), tenant_id=tenant_id, content=content)
    if idem_key:
        store.complete_idempotency(tenant_id=tenant_id, operation="upload", key=idem_key, response=result.model_dump())
    return result


@app.post("/api/cases/{case_id}/ask", response_model=AskResponse)
def ask(case_id: str, request: AskRequest) -> AskResponse:
    if case_id != pilot.case["case_id"]: raise HTTPException(status_code=404, detail="Case not found")
    return pilot.ask(request.question)

@app.post("/api/cases/{case_id}/completeness", response_model=CompletenessReport)
def completeness(case_id: str) -> CompletenessReport:
    if case_id != pilot.case["case_id"]: raise HTTPException(status_code=404, detail="Case not found")
    return pilot.completeness()

@app.post("/api/cases/{case_id}/evidence", response_model=EvidenceResponse)
def evidence(case_id: str, request: EvidenceRequest) -> EvidenceResponse:
    if case_id != pilot.case["case_id"]: raise HTTPException(status_code=404, detail="Case not found")
    return pilot.evidence_check(request.claim)

@app.post("/api/cases/{case_id}/review-memo", response_model=ReviewMemo)
def review_memo(case_id: str) -> ReviewMemo:
    if case_id != pilot.case["case_id"]: raise HTTPException(status_code=404, detail="Case not found")
    return pilot.review_memo()

@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    feedback_id, eval_case = store.save_feedback(payload.model_dump(), tenant_id=_tenant_id(request))
    return FeedbackResponse(feedback_id=feedback_id, stored=True, persistence_mode=store.mode, eval_case=eval_case)

@app.get("/api/feedback")
def list_feedback(request: Request) -> dict:
    return {"persistence_mode": store.mode, "items": store.list_feedback(tenant_id=_tenant_id(request))}

@app.post("/api/benchmark/run", response_model=BenchmarkReport)
def benchmark(payload: BenchmarkRunRequest, request: Request) -> BenchmarkReport:
    report = run_benchmark(payload.providers)
    store.save_benchmark(report.run_id, report.model_dump(), tenant_id=_tenant_id(request))
    return report

@app.delete("/api/tenants/me/data")
def delete_current_tenant_data(request: Request) -> dict:
    principal = _principal(request)
    if production_mode and (not principal or principal.role not in {"admin", "owner"}):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    tenant_id = _tenant_id(request)
    return {"tenant_id": tenant_id, "deleted": store.delete_tenant(tenant_id), "status": "deleted"}

@app.get("/api/product-brief")
def product_brief() -> dict:
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
        "production_v1": [
            "tenant-bound production API principals", "durable Postgres metadata + original PDF BYTEA storage",
            "idempotent upload writes", "tenant-scoped deletion", "storage health + fail-closed readiness",
        ],
        "production_next": [
            "DMS/funding-system adapters", "measured SLOs + restore drill evidence",
            "qualified reviewer + external security validation",
        ],
        "external_next": [
            "DMS/funding-system adapters", "measured SLOs + restore drill evidence",
            "qualified reviewer + external security validation",
        ],
    }

if not os.getenv("VERCEL"):
    public_dir = Path(__file__).resolve().parents[1] / "public"
    if public_dir.is_dir(): app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
