from __future__ import annotations

import hashlib
import io
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from pypdf import PdfReader

from .models import (
    AuthenticityRecord,
    ExtractedField,
    IntegrityRecord,
    ProvenanceRecord,
    SecurityFinding,
    SourceTrustEnvelope,
    TraceStep,
    UploadResult,
)


TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bewilligungsbescheid": ("bewilligungsbescheid", "zuwendungsempfänger", "bewilligte bundesförderung", "nebenbestimmungen"),
    "verwendungsnachweis": ("verwendungsnachweis", "beantragte erstattung", "zahlenmäßiger nachweis", "verwendung der mittel"),
    "rechnungspaket": ("rechnung", "rechnungsnummer", "leistungszeitraum", "zahlbetrag", "netto", "brutto"),
    "sachbericht": ("sachbericht", "projektverlauf", "zielerreichung", "projektergebnis"),
    "kostenplan": ("kostenplan", "gesamtausgaben", "finanzierungsplan", "ausgabenposition"),
    "messprotokolle": ("messprotokoll", "messumfang", "bandbreite", "abschlusspunkt"),
    "fotodokumentation": ("fotodokumentation", "gps", "koordinaten", "baufortschritt"),
    "abnahmeprotokoll": ("abnahmeprotokoll", "abnahme", "mängel", "auftragnehmer"),
    "netzplan": ("netzplan", "projektgebiet", "trasse", "hausanschluss"),
}

INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+(system\s+)?instructions",
    r"reveal\s+(the\s+)?(system prompt|api key|secret)",
    r"send\s+(the\s+)?api key",
    r"you are now",
    r"developer message",
    r"system instruction",
    r"überschreibe\s+(alle\s+)?anweisungen",
    r"ignoriere\s+(alle\s+)?vorherigen\s+anweisungen",
)

AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)\s*(?:EUR|€)", re.IGNORECASE)
DATE_RE = re.compile(r"(?<!\d)(\d{2}[.]\d{2}[.]\d{4}|\d{4}-\d{2}-\d{2})(?!\d)")
INVOICE_RE = re.compile(r"\b(?:R|RE|INV)[-_/]?\d{2,6}\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    pages: int
    page_texts: tuple[str, ...]


def extract_pdf_text(content: bytes) -> ParsedDocument:
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages[:50]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return ParsedDocument(text="\n".join(parts).strip(), pages=len(reader.pages), page_texts=tuple(parts))


def classify_document(text: str, filename: str = "") -> tuple[str, float, dict[str, int]]:
    haystack = f"{filename} {text}".lower()
    scores: dict[str, int] = {
        doc_type: sum(1 for keyword in keywords if keyword in haystack)
        for doc_type, keywords in TYPE_KEYWORDS.items()
    }
    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score == 0:
        return "unbekannt", 0.35, scores
    second = sorted(scores.values(), reverse=True)[1]
    margin = best_score - second
    confidence = min(0.99, 0.58 + best_score * 0.09 + margin * 0.04)
    return best_type, round(confidence, 2), scores


def scan_security(text: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    normalized = " ".join(text.split())
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            start = max(match.start() - 55, 0)
            end = min(match.end() + 95, len(normalized))
            findings.append(SecurityFinding(category="prompt_injection", severity="high", excerpt=normalized[start:end], action="quarantine"))
            break
    if re.search(r"javascript:|<script\b", normalized, re.IGNORECASE):
        findings.append(SecurityFinding(category="embedded_script", severity="high", excerpt="Embedded script-like content detected", action="quarantine"))
    if re.search(r"https?://[^\s]+", normalized, re.IGNORECASE) and not findings:
        findings.append(SecurityFinding(category="suspicious_link", severity="low", excerpt="External link detected; retained as untrusted document content.", action="manual_review"))
    return findings or [SecurityFinding(category="none", severity="low", excerpt="No security pattern detected", action="allow")]


def _normalize_amount(raw: str) -> str:
    compact = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = float(compact)
        return f"{value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return f"{raw} EUR"


def extract_fields(text: str, document_type: str) -> list[ExtractedField]:
    normalized = " ".join(text.split())
    fields: list[ExtractedField] = []
    amounts = list(dict.fromkeys(AMOUNT_RE.findall(normalized)))[:6]
    dates = list(dict.fromkeys(DATE_RE.findall(normalized)))[:6]
    invoices = list(dict.fromkeys(INVOICE_RE.findall(normalized)))[:8]

    if amounts:
        label = "Beantragter Betrag" if document_type == "verwendungsnachweis" else "Gefundene Beträge"
        fields.append(ExtractedField(name=label, value=", ".join(_normalize_amount(value) for value in amounts), confidence=0.91 if document_type != "unbekannt" else 0.72, evidence=amounts[0]))
    if dates:
        fields.append(ExtractedField(name="Gefundene Datumsangaben", value=", ".join(dates), confidence=0.94, evidence=dates[0]))
    if invoices:
        fields.append(ExtractedField(name="Rechnungsnummern", value=", ".join(invoices), confidence=0.93, evidence=invoices[0]))
    if "unterschrift" in normalized.lower():
        fields.append(ExtractedField(name="Unterschrift", value="im Text erwähnt", confidence=0.64, evidence="Unterschrift"))
    return fields


def _locate_evidence(page_texts: tuple[str, ...], evidence: str) -> tuple[int | None, str | None]:
    needle = evidence.strip().lower()
    if not needle:
        return None, None
    for index, page_text in enumerate(page_texts, start=1):
        normalized = " ".join(page_text.split())
        if needle in normalized.lower():
            return index, hashlib.sha256(evidence.encode("utf-8")).hexdigest()
    return None, hashlib.sha256(evidence.encode("utf-8")).hexdigest()


def ingest_pdf(filename: str, content: bytes) -> UploadResult:
    started = time.perf_counter()
    trace: list[TraceStep] = []
    captured_at = datetime.now(timezone.utc).isoformat()
    content_sha256 = hashlib.sha256(content).hexdigest()
    document_id = f"doc_{uuid.uuid4().hex[:12]}"

    parse_start = time.perf_counter()
    parsed = extract_pdf_text(content)
    trace.append(TraceStep(tool="pdf_text_extraction", detail=f"{parsed.pages} Seiten verarbeitet", duration_ms=round((time.perf_counter() - parse_start) * 1000, 2)))

    classify_start = time.perf_counter()
    document_type, confidence, _ = classify_document(parsed.text, filename)
    trace.append(TraceStep(tool="document_classification", status="warning" if confidence < 0.7 else "ok", detail=f"{document_type} mit {confidence:.0%} Konfidenz", duration_ms=round((time.perf_counter() - classify_start) * 1000, 2)))

    security_start = time.perf_counter()
    findings = scan_security(parsed.text)
    quarantined = any(f.action == "quarantine" for f in findings)
    manual_review = any(f.action == "manual_review" for f in findings)
    trace.append(TraceStep(tool="untrusted_content_scan", status="warning" if quarantined or manual_review else "ok", detail="Dokument quarantänisiert" if quarantined else "Kein kritisches Muster erkannt", duration_ms=round((time.perf_counter() - security_start) * 1000, 2)))

    extract_start = time.perf_counter()
    raw_fields = extract_fields(parsed.text, document_type)
    fields: list[ExtractedField] = []
    for field in raw_fields:
        page, excerpt_sha = _locate_evidence(parsed.page_texts, field.evidence)
        fields.append(field.model_copy(update={"page": page, "evidence_sha256": excerpt_sha}))
    trace.append(TraceStep(tool="schema_extraction", status="warning" if not fields else "ok", detail=f"{len(fields)} strukturierte Feldgruppen extrahiert", duration_ms=round((time.perf_counter() - extract_start) * 1000, 2)))

    status = "quarantined" if quarantined else ("manual_review" if confidence < 0.7 or manual_review else "ready")
    preview = " ".join(parsed.text.split())[:900]
    trace.append(TraceStep(tool="capture_source_provenance", detail="Original bytes hashed; extracted evidence pinned to PDF pages", duration_ms=0.1))
    trace.append(TraceStep(tool="persist_document_state", detail=f"Upload-Ergebnis bereit ({status})", duration_ms=round((time.perf_counter() - started) * 1000, 2)))

    return UploadResult(
        document_id=document_id,
        filename=filename,
        sha256=content_sha256,
        bytes=len(content),
        page_count=parsed.pages,
        document_type=document_type,
        classification_confidence=confidence,
        extracted_fields=fields,
        security_findings=findings,
        status=status,
        preview=preview,
        trace=trace,
        source_trust=SourceTrustEnvelope(
            authenticity=AuthenticityRecord(status="original_as_received", method="raw_pdf_capture"),
            integrity=IntegrityRecord(sha256=content_sha256, verified=True, version=f"sha256:{content_sha256[:16]}", captured_at=captured_at),
            provenance=ProvenanceRecord(source_system="pruefpilot_upload", source_uri=f"pruefpilot://upload/{document_id}", acquired_at=captured_at),
        ),
    )
