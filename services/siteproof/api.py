import uuid
from datetime import UTC
from functools import wraps
from urllib.parse import urlsplit

import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .security import valid_phone, validate_url
from .storage import client

app = FastAPI(title="SiteProof", version="0.1.0")


class CreateJob(BaseModel):
    url: str = Field(max_length=2048)
    goal: str = Field(default="", max_length=500)


class Approve(BaseModel):
    finding_ids: list[str] = []
    fact_ids: list[str] = []


class Review(BaseModel):
    decision: str


def tenant(x_tenant_key: str = Header("")):
    import secrets

    for tenant_id, key in settings.tenant_keys().items():
        if secrets.compare_digest(x_tenant_key, key):
            return tenant_id
    raise HTTPException(401, detail={"code": "unauthorized", "message": "Valid tenant credential required"})


def job_or_404(tenant, job_id):
    job = db.get_job(tenant, job_id)
    if not job:
        raise HTTPException(404, detail={"code": "not_found", "message": "Job not found"})
    return job


def serialized_job_mutation(handler):
    @wraps(handler)
    def wrapped(job_id, *args, **kwargs):
        try:
            with db.locked_job(kwargs["t"], job_id):
                return handler(job_id, *args, **kwargs)
        except LookupError as exc:
            raise HTTPException(404, detail={"code": "not_found", "message": "Job not found"}) from exc

    return wrapped


def enqueue(tenant, job_id, url, action="audit"):
    payload = {"tenant": tenant, "job_id": job_id, "action": action, "domain": urlsplit(url).hostname}
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO task_outbox(tenant_id,job_id,payload) VALUES(%s,%s,%s)", (tenant, job_id, Jsonb(payload))
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        redis.Redis.from_url(settings.redis_url).ping()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(503, "Dependencies unavailable") from exc


@app.post("/api/jobs", status_code=201)
def create(body: CreateJob, t: str = Depends(tenant), idempotency_key: str = Header("", max_length=128)):
    if not idempotency_key:
        raise HTTPException(422, detail={"code": "idempotency_required", "message": "Idempotency-Key header required"})
    if settings.mode == "live" and not settings.model_key:
        raise HTTPException(
            503, detail={"code": "credentials_missing", "message": "SITEPROOF_MODEL_KEY required in live mode"}
        )
    if settings.mode == "live" and not settings.embedding_credential():
        raise HTTPException(
            503,
            detail={
                "code": "embedding_credentials_missing",
                "message": "Set SITEPROOF_EMBEDDING_KEY or explicitly enable SITEPROOF_EMBEDDING_USE_MODEL_CREDENTIALS",
            },
        )
    if settings.mode == "live" and settings.require_known_prices and not settings.prices_known():
        raise HTTPException(
            503, detail={"code": "pricing_missing", "message": "Monetary policy requires all three prices"}
        )
    try:
        fixture = settings.mode == "fixture" and body.url.startswith("https://fixture.siteproof.test/")
        url = validate_url(body.url, resolve=not fixture)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "unsafe_url", "message": str(exc)}) from exc
    identifier = str(uuid.uuid4())
    data = {
        "validation_session": settings.live_validation_session if settings.mode == "live" else None,
        "goal": body.goal,
        "fixture": settings.mode == "fixture",
        "budget": {
            "max_tokens": 12000,
            "max_tool_calls": 20,
            "max_seconds": 180,
            "max_cost": 1 if settings.mode != "live" or settings.prices_known() else None,
            "cost": None,
        },
        "versions": {"prompt": "auditor-v2", "guidance": "guidance-v1", "renderer": "components-v1"},
    }
    with db.connection() as conn:
        created = conn.execute(
            "INSERT INTO audit_jobs(id,tenant_id,idempotency_key,submitted_url,canonical_url,data) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,idempotency_key) DO NOTHING RETURNING *",
            (identifier, t, idempotency_key, body.url, url, Jsonb(data)),
        ).fetchone()
        if not created:
            existing = conn.execute(
                "SELECT * FROM audit_jobs WHERE tenant_id=%s AND idempotency_key=%s", (t, idempotency_key)
            ).fetchone()
            if existing["submitted_url"] != body.url or existing["data"].get("goal", "") != body.goal:
                raise HTTPException(409, "Idempotency key already used for another request")
            return existing
        if settings.mode == "live":
            from .live_limits import allocate

            try:
                allocate(t, settings.live_validation_session, "audit")
            except ValueError as exc:
                raise HTTPException(409, detail={"code": "validation_budget", "message": str(exc)}) from exc
        payload = {"tenant": t, "job_id": identifier, "action": "audit", "domain": urlsplit(url).hostname}
        conn.execute(
            "INSERT INTO task_outbox(tenant_id,job_id,payload) VALUES(%s,%s,%s)", (t, identifier, Jsonb(payload))
        )
    return created


@app.get("/api/jobs")
def jobs(t: str = Depends(tenant)):
    with db.connection() as conn:
        return {
            "jobs": conn.execute(
                "SELECT * FROM audit_jobs WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 100", (t,)
            ).fetchall()
        }


@app.get("/api/jobs/{job_id}")
def detail(job_id: str, t: str = Depends(tenant)):
    return job_or_404(t, job_id)


@app.get("/api/jobs/{job_id}/{kind}")
def items(job_id: str, kind: str, t: str = Depends(tenant)):
    job = job_or_404(t, job_id)
    if kind == "guidance":
        if "guidance_snapshot" in job["data"]:
            return {"items": job["data"]["guidance_snapshot"]}
        ids = job["data"].get("guidance_ids", [])
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT c.id,c.content,d.source,d.version,d.retrieved_at,d.reuse_notes "
                "FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id AND d.tenant_id=c.tenant_id "
                "WHERE c.tenant_id=%s AND d.collection='guidance' AND c.id=ANY(%s) ORDER BY c.id",
                (t, ids),
            ).fetchall()
        return {"items": rows}
    mapping = {
        "evidence": "Evidence",
        "findings": "Finding",
        "facts": "BusinessFact",
        "verification": "VerificationResult",
        "runs": "ModelRun",
        "captures": "Capture",
    }
    if kind == "preview-html":
        designs = db.records(t, job_id, "Redesign")
        if not designs:
            raise HTTPException(404, "Preview not yet generated")
        return Response(
            designs[-1]["html"],
            media_type="text/html",
            headers={
                "Cache-Control": "private, no-store",
                "X-Robots-Tag": "noindex,nofollow",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'",
            },
        )
    if kind == "preview":
        designs = db.records(t, job_id, "Redesign")
        if not designs:
            raise HTTPException(404, "Preview not yet generated")
        return designs[-1]["spec"]
    if kind not in mapping:
        raise HTTPException(404, "Unknown resource")
    return {"items": db.records(t, job_id, mapping[kind])}


@app.post("/api/jobs/{job_id}/approve")
@serialized_job_mutation
def approve(job_id: str, body: Approve, t: str = Depends(tenant)):
    job = job_or_404(t, job_id)
    if job["status"] != "needs_review":
        raise HTTPException(409, "Approvals require review stage")
    for kind, ids in [("Finding", body.finding_ids), ("BusinessFact", body.fact_ids)]:
        items = db.records(t, job_id, kind)
        if not set(ids) <= {i["id"] for i in items}:
            raise HTTPException(422, "Unknown approval IDs")
        for item in items:
            if item["id"] in ids:
                item["approved"] = True
        db.save_records(t, job_id, kind, items)
        if kind == "BusinessFact":
            db.index_business_facts(t, job_id, items)
    db.save_records(
        t,
        job_id,
        "ReviewDecision",
        [
            {
                "id": str(uuid.uuid4()),
                "decision": "approve_inputs",
                "finding_ids": body.finding_ids,
                "fact_ids": body.fact_ids,
            }
        ],
    )
    return {"status": "approved"}


@app.post("/api/jobs/{job_id}/redesign")
@serialized_job_mutation
def redesign(job_id: str, t: str = Depends(tenant)):
    job = job_or_404(t, job_id)
    if job["status"] != "needs_review":
        raise HTTPException(409, "Audit must finish before redesign")
    findings = db.records(t, job_id, "Finding")
    facts = db.records(t, job_id, "BusinessFact")
    if any(not f.get("approved") for f in findings + facts):
        raise HTTPException(409, "Approve all findings and business facts before redesign")
    with db.connection() as conn:
        changed = conn.execute(
            "UPDATE audit_jobs SET status='designing',stage='designing',data=jsonb_set(data,'{redesign_revision}',to_jsonb(COALESCE((data->>'redesign_revision')::int,0)+1)),updated_at=now() WHERE id=%s AND tenant_id=%s AND status='needs_review' RETURNING id,data",
            (job_id, t),
        ).fetchone()
        if not changed:
            raise HTTPException(409, "Redesign already queued or unavailable")
        payload = {
            "tenant": t,
            "job_id": job_id,
            "action": "redesign",
            "revision": changed["data"]["redesign_revision"],
            "domain": urlsplit(job["canonical_url"]).hostname,
        }
        conn.execute("INSERT INTO task_outbox(tenant_id,job_id,payload) VALUES(%s,%s,%s)", (t, job_id, Jsonb(payload)))
    return {"status": "designing"}


@app.post("/api/jobs/{job_id}/review")
@serialized_job_mutation
def review(job_id: str, body: Review, t: str = Depends(tenant)):
    job = job_or_404(t, job_id)
    if body.decision not in ("accept", "reject"):
        raise HTTPException(422, "Decision must be accept or reject")
    if job["status"] != "needs_review":
        raise HTTPException(409, "Preview review requires needs_review stage")
    results = db.records(t, job_id, "VerificationResult")
    if not results:
        raise HTTPException(409, "No tested preview is available for review")
    if body.decision == "accept" and (
        not results or not results[-1]["required_checks_passed"] or job["status"] != "needs_review"
    ):
        raise HTTPException(409, "Failed or unavailable required verification prevents acceptance")
    db.save_records(t, job_id, "ReviewDecision", [{"id": str(uuid.uuid4()), "decision": body.decision}])
    db.update_job(t, job_id, "completed" if body.decision == "accept" else "needs_review")
    return {"status": "completed" if body.decision == "accept" else "needs_review"}


@app.post("/api/jobs/{job_id}/cancel")
@serialized_job_mutation
def cancel(job_id: str, t: str = Depends(tenant)):
    job = job_or_404(t, job_id)
    if job["status"] == "completed":
        raise HTTPException(409, "Completed jobs cannot be cancelled")
    db.update_job(t, job_id, "cancelled")
    return {"status": "cancelled"}


@app.get("/api/artifacts/{job_id}/{artifact_id}")
def artifact(job_id: str, artifact_id: str, t: str = Depends(tenant)):
    job_or_404(t, job_id)
    item = next(
        (e for e in db.records(t, job_id, "Evidence") if e["id"] == artifact_id and e["kind"] == "screenshot"), None
    )
    if not item:
        raise HTTPException(404, "Artifact not found")
    obj = client().get_object(Bucket=settings.s3_bucket, Key=item["artifact_key"])
    return Response(
        obj["Body"].read(),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"},
    )


@app.get("/api/jobs/{job_id}/preview-html")
def preview_html(job_id: str, t: str = Depends(tenant)):
    job_or_404(t, job_id)
    designs = db.records(t, job_id, "Redesign")
    if not designs:
        raise HTTPException(404, "Preview not yet generated")
    return Response(
        designs[-1]["html"],
        media_type="text/html",
        headers={
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex,nofollow",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'",
        },
    )


class CorrectFact(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)


@app.post("/api/jobs/{job_id}/facts/{fact_id}/correct")
@serialized_job_mutation
def correct_fact(job_id: str, fact_id: str, body: CorrectFact, t: str = Depends(tenant)):
    import re
    from datetime import datetime

    job = job_or_404(t, job_id)
    if job["status"] != "needs_review":
        raise HTTPException(409, "Fact corrections require review stage")
    facts = db.records(t, job_id, "BusinessFact")
    fact = next((f for f in facts if f["id"] == fact_id), None)
    if not fact:
        raise HTTPException(404, "Fact not found")
    if fact["kind"] == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", body.value):
        raise HTTPException(422, "Invalid email correction")
    if fact["kind"] == "phone" and not valid_phone(body.value):
        raise HTTPException(422, "Invalid phone correction")
    fact.setdefault("corrections", []).append(
        {
            "previous_value": fact["value"],
            "corrected_value": body.value,
            "reason": body.reason,
            "actor_tenant_id": t,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    fact["value"] = body.value
    fact["approved"] = True
    if fact["kind"] in ("phone", "email"):
        fact["href"] = ("mailto:" if fact["kind"] == "email" else "tel:") + body.value
    db.save_records(t, job_id, "BusinessFact", facts)
    db.index_business_facts(t, job_id, facts)
    db.update_job(t, job_id, "needs_review", {"verification_passed": False})
    # Existing preview becomes stale and cannot be accepted after fact correction.
    with db.connection() as conn:
        conn.execute(
            "DELETE FROM records WHERE tenant_id=%s AND job_id=%s AND kind IN ('Redesign','VerificationResult')",
            (t, job_id),
        )
    return fact


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str, t: str = Depends(tenant)):
    from .retention import delete_job

    job_or_404(t, job_id)
    try:
        return delete_job(t, job_id)
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "deletion_busy", "message": str(exc)}) from exc
    except LookupError as exc:
        raise HTTPException(404, "Job not found") from exc
