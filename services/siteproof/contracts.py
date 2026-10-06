from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    id: str
    category: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    claim: str
    evidence_ids: list[str] = Field(min_length=1)
    guidance_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    kind: Literal["objective_defect", "design_hypothesis"]
    proposed_change: str
    verification_method: str
    approved: bool = False


class BusinessFact(BaseModel):
    id: str
    kind: str
    value: str
    source_url: str
    evidence_id: str
    captured_at: str
    approved: bool = False


class PageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=2000)
    layout: Literal["editorial", "classic", "compact"] = "editorial"
    typography: Literal["sans", "serif"] = "sans"
    headline: str = Field(max_length=2000)
    about: str = Field(max_length=10000)
    services: list[str] = Field(max_length=100)
    details: list[str] = Field(default_factory=list, max_length=100)
    contacts: list[dict[str, str]] = Field(max_length=30)
    fixture: bool


class Budget(BaseModel):
    max_tokens: int = 12000
    max_tool_calls: int = 20
    max_seconds: int = 180
    max_cost: float | None = Field(default=1.0, ge=0)
    cost_unknown: bool = False
    tokens: int = 0
    tool_calls: int = 0
    elapsed_seconds: float = 0
    cost: float | None = None

    def consume(self, tokens=0, calls=1, elapsed=0, cost=None):
        if tokens < 0 or calls < 0 or elapsed < 0 or (cost is not None and cost < 0):
            raise ValueError("Budget usage cannot be negative")
        self.elapsed_seconds = max(self.elapsed_seconds, elapsed)
        self.tokens += tokens
        self.tool_calls += calls
        if tokens > 0 and cost is None:
            self.cost_unknown = True
        if self.cost_unknown:
            self.cost = None
        elif cost is not None:
            self.cost = (self.cost or 0) + cost
        if self.tokens > self.max_tokens or self.tool_calls > self.max_tool_calls or elapsed > self.max_seconds:
            raise ValueError("Budget exceeded")
        if self.max_cost is not None and self.cost is not None and self.cost > self.max_cost:
            raise ValueError("Money budget exceeded")


def validate_findings(findings: list[dict], evidence: list[dict]) -> list[dict]:
    ids = {e["id"] for e in evidence}
    result = []
    seen = set()
    for raw in findings:
        finding = Finding.model_validate(raw)
        if not set(finding.evidence_ids) <= ids:
            raise ValueError("Finding references nonexistent evidence")
        key = (finding.kind, finding.category, tuple(sorted(finding.evidence_ids)), finding.claim.strip().casefold())
        if key not in seen:
            seen.add(key)
            result.append(finding.model_dump())
    return result


def preserve_facts(spec: PageSpec, facts: list[dict]):
    """Protect fact values in their semantic sections and contact destinations."""
    import re
    from urllib.parse import unquote

    for fact in facts:
        kind, value = fact["kind"], fact["value"]
        if kind in ("email", "phone"):
            contacts = [item for item in spec.contacts if item.get("kind") == kind and item.get("value") == value]
            if not contacts:
                raise ValueError("Critical business fact was changed or omitted")
            expected = fact.get("href", ("mailto:" if kind == "email" else "tel:") + value)
            normalize = (
                (lambda text: re.sub(r"[(). \-]", "", text)) if kind == "phone" else (lambda text: unquote(text))
            )
            if not any(normalize(item.get("href", "")) == normalize(expected) for item in contacts):
                raise ValueError("Critical contact destination was changed")
        elif kind == "service" and value not in spec.services:
            raise ValueError("Captured service was changed or omitted")
        elif kind in ("hours", "price") and value not in spec.details:
            raise ValueError("Captured hours or price was changed or omitted")


class OwnedRecord(BaseModel):
    id: str
    tenant_id: str


class Tenant(BaseModel):
    id: str
    name: str


class AuditJob(OwnedRecord):
    submitted_url: str
    canonical_url: str
    status: Literal[
        "queued", "capturing", "auditing", "designing", "verifying", "needs_review", "completed", "failed", "cancelled"
    ]
    stage: str
    created_at: str
    updated_at: str
    data: dict
    retry_count: int
    error: dict | None = None


class Capture(OwnedRecord):
    partial: bool
    viewport_settings: dict


class Evidence(OwnedRecord):
    kind: Literal["screenshot", "dom", "axe", "lighthouse", "check", "unavailable"]
    viewport: str | None = None
    data: dict | None = None


class KnowledgeDocument(OwnedRecord):
    collection: Literal["business_facts", "guidance"]
    source: str
    retrieved_at: str
    version: str
    reuse_notes: str


class KnowledgeChunk(OwnedRecord):
    document_id: str
    content: str
    content_hash: str
    embedding: list[float] | None = None


class Redesign(OwnedRecord):
    spec: PageSpec
    html: str
    version: str


class VerificationResult(OwnedRecord):
    results: list[dict]
    regressions: list[str]
    facts_preserved: bool
    required_checks_passed: bool


class ModelRun(OwnedRecord):
    model: str
    prompt_version: str
    tokens: int
    duration_ms: int
    cost: float | None
    fixture: bool


class ReviewDecision(OwnedRecord):
    decision: str
