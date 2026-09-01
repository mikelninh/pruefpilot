from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    tool: str
    status: Literal["ok", "warning", "error"] = "ok"
    detail: str
    duration_ms: float = 0.0


class Citation(BaseModel):
    source_id: str
    title: str
    version: str
    page: int
    section: str
    source_url: str
    confidence: float = Field(ge=0.0, le=1.0)


class AuthenticityRecord(BaseModel):
    status: Literal["unverified", "original_as_received", "verified_issuer"]
    method: str


class IntegrityRecord(BaseModel):
    sha256: str
    verified: bool
    version: str
    captured_at: str


class ProvenanceRecord(BaseModel):
    source_system: str
    source_uri: str
    acquired_at: str


class SourceTrustEnvelope(BaseModel):
    authenticity: AuthenticityRecord
    integrity: IntegrityRecord
    provenance: ProvenanceRecord


class EvidenceLocator(BaseModel):
    kind: Literal["page", "paragraph", "section", "row", "field", "record"]
    value: str


class FindingEvidence(BaseModel):
    id: str
    source_id: str
    locator: EvidenceLocator
    excerpt: str
    excerpt_sha256: str


class AuthorityRecord(BaseModel):
    id: str
    title: str
    version: str
    source_url: str
    status: Literal["authoritative", "case_specific"]


class DerivationRecord(BaseModel):
    summary: str
    method: str
    evidence_ids: list[str]


class HumanDecisionRecord(BaseModel):
    required: bool = True
    status: Literal["pending", "approved", "rejected"] = "pending"
    actor_id: str | None = None
    decided_at: str | None = None


class AuditAnchor(BaseModel):
    trace_id: str
    created_at: str


class FindingTrustChain(BaseModel):
    version: Literal["trust-chain/v1"] = "trust-chain/v1"
    finding_id: str
    subject_type: str
    subject_id: str
    authenticity: AuthenticityRecord
    integrity: IntegrityRecord
    provenance: ProvenanceRecord
    authority: AuthorityRecord
    evidence: list[FindingEvidence]
    derivation: DerivationRecord
    human_decision: HumanDecisionRecord
    audit: AuditAnchor
    assurance: Literal["insufficient", "traceable", "verified"]
    production_eligible: bool
    blockers: list[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    trace: list[TraceStep]
    grounded: bool
    uncertainty: Literal["low", "medium", "high"]


class CompletenessItem(BaseModel):
    document_type: str
    title: str
    status: Literal["present", "missing", "review"]


class CompletenessReport(BaseModel):
    present: int
    required: int
    missing: list[CompletenessItem]
    review_flags: list[str]
    trace: list[TraceStep]


class EvidenceRequest(BaseModel):
    claim: str = Field(min_length=3, max_length=600)


class EvidenceResponse(BaseModel):
    status: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"]
    summary: str
    supporting_evidence: list[str]
    missing_evidence: list[str]
    trace: list[TraceStep]


class ReviewMemo(BaseModel):
    case_id: str
    decision: Literal["READY_FOR_REVIEW", "NEEDS_INFORMATION"]
    confirmed: list[str]
    open_points: list[str]
    next_actions: list[str]
    citations: list[Citation]
    trace: list[TraceStep]
    human_approval_required: bool = True
    trust_chains: list[FindingTrustChain] = Field(default_factory=list)


class SecurityFinding(BaseModel):
    category: Literal["prompt_injection", "suspicious_link", "embedded_script", "none"]
    severity: Literal["low", "medium", "high"]
    excerpt: str
    action: Literal["allow", "quarantine", "manual_review"]


class ExtractedField(BaseModel):
    name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    page: int | None = None
    evidence_sha256: str | None = None


class UploadResult(BaseModel):
    document_id: str
    filename: str
    sha256: str
    bytes: int
    page_count: int
    document_type: str
    classification_confidence: float = Field(ge=0.0, le=1.0)
    extracted_fields: list[ExtractedField]
    security_findings: list[SecurityFinding]
    status: Literal["ready", "quarantined", "manual_review"]
    preview: str
    trace: list[TraceStep]
    source_trust: SourceTrustEnvelope


class FeedbackRequest(BaseModel):
    case_id: str = "GF-2026-014"
    document_id: str
    field_name: str
    previous_value: str
    corrected_value: str
    note: str = Field(default="", max_length=1000)


class FeedbackResponse(BaseModel):
    feedback_id: str
    stored: bool
    persistence_mode: str
    eval_case: dict[str, Any]


class BenchmarkRunRequest(BaseModel):
    providers: list[Literal["deterministic", "openai", "mistral", "local"]] = ["deterministic"]


class BenchmarkMetric(BaseModel):
    provider: str
    status: Literal["measured", "not_configured", "failed"]
    classification_accuracy: float | None = None
    extraction_accuracy: float | None = None
    security_recall: float | None = None
    structured_output_rate: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    estimated_cost_eur: float | None = None
    cases: int = 0
    note: str = ""


class BenchmarkReport(BaseModel):
    run_id: str
    generated_at: str
    metrics: list[BenchmarkMetric]
    methodology: list[str]


class QueueItem(BaseModel):
    case_id: str
    applicant: str
    stage: str
    risk_score: int
    open_points: int
    next_action: str


class CaseSummary(BaseModel):
    case_id: str
    title: str
    applicant: str
    project_period: dict[str, str]
    documents_present: int
    documents_required: int
    amount_delta_eur: int
    risk_score: int
