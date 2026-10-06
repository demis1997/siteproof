"""One operator-triggered live audit; shared allocation and inspectable review report."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
from siteproof.config import settings
from siteproof.db import connection
from siteproof.retrieval import embedding_identity
from siteproof.security import validate_url


def code_commit():
    if os.getenv("SITEPROOF_CODE_COMMIT"):
        return os.environ["SITEPROOF_CODE_COMMIT"]
    try:
        return (
            subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
            or None
        )
    except OSError:
        return None


def safe_endpoint(value):
    parsed = urlsplit(value)
    return parsed.scheme + "://" + (parsed.hostname or "") + parsed.path


def inspect_findings(findings, evidence, guidance):
    evidence_map = {e["id"]: e for e in evidence}
    sources = {g["id"]: g for g in guidance}
    reviews = []
    for finding in findings:
        refs = finding["evidence_ids"]
        guidance_ids = finding.get("guidance_ids", [])
        missing = set(refs) - evidence_map.keys() or set(guidance_ids) - sources.keys()
        objective = finding["kind"] == "objective_defect"
        supported = objective and any(
            evidence_map.get(i, {}).get("passed") is False or evidence_map.get(i, {}).get("kind") == "axe" for i in refs
        )
        status = (
            "unsupported" if missing or (objective and not supported) else "supported" if supported else "uncertain"
        )
        reviews.append(
            {
                "claim": finding["claim"],
                "kind": finding["kind"],
                "evidence_ids": refs,
                "guidance_ids": guidance_ids,
                "evidence": [
                    {
                        "id": i,
                        "kind": evidence_map.get(i, {}).get("kind"),
                        "name": evidence_map.get(i, {}).get("name"),
                        "passed": evidence_map.get(i, {}).get("passed"),
                    }
                    for i in refs
                ],
                "guidance": [{"id": i, "source": sources.get(i, {}).get("source")} for i in guidance_ids],
                "support": status,
                "suggested_correction": "Remove or re-ground unsupported claim"
                if status == "unsupported"
                else "Human visual review required"
                if status == "uncertain"
                else finding["proposed_change"],
                "assessment_limit": "Executable defect evidence supports category only; wording still needs independent human review.",
            }
        )
    return reviews


def facts_preserved(original, current, evidence):
    ids = {e["id"] for e in evidence}
    saved = {f["id"]: f for f in current}
    for source in original:
        fact = saved.get(source["id"])
        if (
            not fact
            or fact["evidence_id"] not in ids
            or not fact.get("captured_at")
            or fact["source_url"] != source["source_url"]
        ):
            return False
        value = source["value"]
        for correction in fact.get("corrections", []):
            if (
                correction.get("previous_value") != value
                or not correction.get("reason")
                or not correction.get("timestamp")
            ):
                return False
            value = correction["corrected_value"]
        if fact["value"] != value:
            return False
    return True


def run(api, tenant, url=None, session="live-validation-v1", job_id=None):
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "code_commit": code_commit(),
        "mode": settings.mode,
        "status": "BLOCKED",
        "live_audits_submitted": 0,
        "actual_live_tokens": None,
        "cost_usd": None,
        "configuration": {
            "chat_endpoint": safe_endpoint(settings.model_url),
            "chat_model": settings.model_id,
            "embedding_endpoint": safe_endpoint(settings.embedding_endpoint()),
            "embedding_model": settings.embedding_model,
            "embedding_version": settings.embedding_version,
            "dimensions": 1536,
            "credential_sharing": settings.embedding_use_model_credentials,
            "chat_key_present": bool(settings.model_key),
            "embedding_key_present": bool(settings.embedding_credential()),
            "prices_known": settings.prices_known(),
        },
        "limitations": [
            "No exactly-once model execution claim. Request hashes prove transmitted bytes, not remote vision comprehension.",
            "Human design/hypothesis judgments are unverified. Fixture and live results must remain separate.",
        ],
    }
    if not job_id:
        if settings.mode != "live" or not settings.model_key or not settings.embedding_credential():
            report["blocker"] = (
                "Set live mode, SITEPROOF_MODEL_KEY and separate embedding key or explicit sharing. No provider call was attempted."
            )
            return report
        if not url:
            raise ValueError(
                "Provide a controlled public fixture URL; do not enable private-network exceptions in live mode"
            )
        validate_url(url)
    key = os.getenv("SITEPROOF_VALIDATION_TENANT_KEY")
    if not key:
        report["blocker"] = "SITEPROOF_VALIDATION_TENANT_KEY required for authenticated operator API access"
        return report
    headers = {"X-Tenant-Key": key}
    with httpx.Client(base_url=api, headers=headers, timeout=20) as client:
        if not job_id:
            if session != settings.live_validation_session:
                raise ValueError("Use the configured shared live validation session")
            created = client.post(
                "/api/jobs", headers={"Idempotency-Key": "live-validation-" + str(uuid.uuid4())}, json={"url": url}
            )
            created.raise_for_status()
            job_id = created.json()["id"]
            report["live_audits_submitted"] = 1
        started = time.monotonic()
        while True:
            response = client.get("/api/jobs/" + job_id)
            response.raise_for_status()
            job = response.json()
            if job["status"] in ("needs_review", "failed", "cancelled", "completed"):
                break
            if time.monotonic() - started > 600:
                report.update(status="FAIL", job_id=job_id, blocker="Job wait timed out; do not automatically resubmit")
                return report
            time.sleep(2)
        data = {}
        for resource in ("evidence", "findings", "facts", "guidance", "runs"):
            response = client.get(f"/api/jobs/{job_id}/{resource}")
            response.raise_for_status()
            data[resource] = response.json()["items"]
        images = []
        for e in data["evidence"]:
            if e["kind"] == "screenshot":
                response = client.get(e["artifact_url"])
                response.raise_for_status()
                images.append(
                    {
                        "id": e["id"],
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                        "bytes": len(response.content),
                    }
                )
        audit_run = next((r for r in data["runs"] if r["id"] == "audit-model"), {})
        real = not job.get("data", {}).get("fixture", True) and audit_run.get("fixture") is False
        transmitted = audit_run.get("images_sent", [])
        image_match = (
            bool(images)
            and len(images) == len(transmitted)
            and sorted(images, key=lambda x: x["id"]) == sorted(transmitted, key=lambda x: x["id"])
        )
        review = inspect_findings(data["findings"], data["evidence"], data["guidance"])
        embedding_runs = [r for r in data["runs"] if r["id"].startswith("embedding-")]
        with connection() as conn:
            capture = conn.execute(
                "SELECT result FROM workflow_steps WHERE tenant_id=%s AND job_id=%s AND step='capture-v1' AND status='succeeded'",
                (job["tenant_id"], job_id),
            ).fetchone()
        preserved = bool(capture) and facts_preserved(capture["result"]["facts"], data["facts"], data["evidence"])
        vectors_used = (
            audit_run.get("retrieval_strategy") == "hybrid"
            and audit_run.get("embedding_identity") == embedding_identity()
        )
        report.update(
            status="PASS"
            if real
            and image_match
            and preserved
            and vectors_used
            and audit_run.get("response_model")
            and not any(r["support"] == "unsupported" for r in review)
            else "FAIL",
            job_id=job_id,
            job_status=job["status"],
            retry_count=job.get("retry_count"),
            error=job.get("error"),
            images_match_transmitted_bytes=image_match,
            critical_business_facts_preserved=preserved,
            provider_embedding_identity_used=vectors_used,
            runs=data["runs"],
            guidance=data["guidance"],
            finding_review=review,
            fact_provenance=[
                {
                    "id": f["id"],
                    "kind": f["kind"],
                    "source_url": f["source_url"],
                    "evidence_id": f["evidence_id"],
                    "captured_at": f["captured_at"],
                }
                for f in data["facts"]
            ],
            embedding_calls=len(embedding_runs),
            embedding_verification="Provider-returned vectors indexed/cached by actual workflow; inspect embedding identity and SQL evaluation for ranking proof.",
            actual_live_tokens=sum(r.get("tokens", 0) for r in data["runs"]) if real else None,
            cost_usd=job.get("data", {}).get("budget", {}).get("cost"),
            elapsed_seconds=job.get("data", {}).get("budget", {}).get("elapsed_seconds"),
            ui_review="UNVERIFIED: inspect authenticated dashboard for live label, provenance and corrections",
        )
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://api:8000")
    parser.add_argument("--tenant", default="local")
    parser.add_argument("--url")
    parser.add_argument("--job-id")
    parser.add_argument("--session", default="live-validation-v1")
    args = parser.parse_args()
    print(json.dumps(run(args.api, args.tenant, args.url, args.session, args.job_id), indent=2))
