"""Real Compose/HTTP/Playwright integration. Run only against an isolated CI stack."""
import json
import subprocess
import time
import uuid
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"
HEADERS = {"X-Tenant-Key": "integration-key"}
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "infra/compose.yaml", "-f", "infra/compose.integration.yaml", "--profile", "integration", "-p", "siteproof-integration"]


def compose(*args):
    return subprocess.run(COMPOSE + list(args), check=True, capture_output=True, text=True).stdout


def request(method, path, **kwargs):
    response = httpx.request(method, API + path, headers=HEADERS, timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def wait_job(identifier):
    for _ in range(240):
        job = request("GET", f"/api/jobs/{identifier}")
        if job["status"] in ("needs_review", "failed", "cancelled"):
            assert job["status"] == "needs_review", job
            return job
        time.sleep(1)
    raise AssertionError("Job did not reach review")


def main():
    run_id = str(uuid.uuid4())
    report = {"run_id": run_id,"mode": "fixture", "samples": [], "live_audit": "UNVERIFIED: credentials not configured"}
    readiness = "No response"
    for _ in range(120):
        try:
            response = httpx.get(API + "/ready", timeout=2, trust_env=False)
            readiness = f"{response.status_code}: {response.text[:200]}"
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(1)
    else:
        raise AssertionError("Stack not ready: " + readiness)
    for slug in ("clean", "overflow", "broken-contact", "missing-labels", "conflicting-facts", "prompt-injection"):
        url = f"http://fixture.siteproof.test/{slug}"
        headers = dict(HEADERS, **{"Idempotency-Key": "integration-" + run_id + "-" + slug})
        response = httpx.post(API + "/api/jobs", headers=headers, json={"url": url})
        response.raise_for_status()
        job = response.json()
        duplicate = httpx.post(API + "/api/jobs", headers=headers, json={"url": url}).json()
        assert duplicate["id"] == job["id"]
        identifier = job["id"]
        if slug == "clean":
            # Interrupt capture, recover the Redis processing list and persistent LangGraph state.
            time.sleep(2)
            compose("kill", "-s", "SIGKILL", "worker")
            compose("up", "-d", "worker")
        wait_job(identifier)
        evidence = request("GET", f"/api/jobs/{identifier}/evidence")["items"]
        findings = request("GET", f"/api/jobs/{identifier}/findings")["items"]
        facts = request("GET", f"/api/jobs/{identifier}/facts")["items"]
        guidance = request("GET", f"/api/jobs/{identifier}/guidance")["items"]
        assert guidance and all(g["id"].startswith("integration:") and g["source"] and g["version"] for g in guidance)
        ids = {e["id"] for e in evidence}
        assert len(ids) == len(evidence)
        for viewport in ("desktop", "mobile"):
            assert any(e["kind"] == "dom" and e["viewport"] == viewport for e in evidence)
            assert any(e["kind"] == "lighthouse" and e["viewport"] == viewport for e in evidence), [e for e in evidence if e["kind"] == "unavailable"]
            assert any(e.get("name") == "axe" and e["viewport"] == viewport for e in evidence)
            shot = next(e for e in evidence if e["kind"] == "screenshot" and e["viewport"] == viewport)
            image = httpx.get(API + shot["artifact_url"], headers=HEADERS)
            assert image.content.startswith(b"\x89PNG")
            assert httpx.get(API + shot["artifact_url"]).status_code == 401
        assert all(set(f["evidence_ids"]) <= ids for f in findings)
        assert all(f["evidence_id"] in ids and f["captured_at"] and f["source_url"] == url for f in facts)
        assert httpx.get(API + f"/api/jobs/{identifier}", headers={"X-Tenant-Key": "other-key"}).status_code == 404
        if slug == "overflow":
            assert any(e.get("name") == "horizontal_overflow" and e["viewport"] == "mobile" and not e["passed"] for e in evidence)
        if slug == "conflicting-facts":
            assert len({f["value"] for f in facts if f["kind"] == "phone"}) == 2
        if slug == "missing-labels":
            assert any(e["kind"] == "axe" and "label" in e["id"] for e in evidence)
        if slug == "clean":
            fact = next(f for f in facts if f["kind"] == "email")
            request("POST", f"/api/jobs/{identifier}/facts/{fact['id']}/correct", json={"value": "corrected@example.com", "reason": "Integration correction"})
            compose("restart", "api", "worker")
            time.sleep(5)
            saved = request("GET", f"/api/jobs/{identifier}/facts")["items"]
            assert next(f for f in saved if f["id"] == fact["id"])["value"] == "corrected@example.com"
            # Duplicate delivery must not rerun completed graph or duplicate model records.
            payload = json.dumps({"tenant": "integration", "job_id": identifier, "action": "audit", "domain": "fixture.siteproof.test"})
            compose("exec", "-T", "redis", "redis-cli", "LPUSH", "siteproof:queue", payload)
            time.sleep(6)
            assert len(request("GET", f"/api/jobs/{identifier}/runs")["items"]) == 1
        report["samples"].append({"slug": slug, "job_id": identifier, "evidence": len(evidence), "findings": len(findings), "facts": len(facts), "status": "PASS"})
    response = httpx.post(API + "/api/jobs", headers=dict(HEADERS, **{"Idempotency-Key": "integration-timeout-" + run_id}),
                          json={"url": "http://fixture.siteproof.test/timeout"})
    response.raise_for_status()
    timeout_job = response.json()["id"]
    wait_job(timeout_job)
    captures = request("GET", f"/api/jobs/{timeout_job}/captures")["items"]
    assert captures and captures[0]["partial"]
    timeout_evidence = request("GET", f"/api/jobs/{timeout_job}/evidence")["items"]
    assert any(e["kind"] == "unavailable" and e["name"] == "capture" for e in timeout_evidence)
    report["timeout"] = {"job_id": timeout_job, "partial": True, "status": "PASS"}
    # Test the trusted dashboard separately; never attach the untrusted capture browser to control services.
    compose("run", "-T", "--name", "siteproof-integration-ui-proof", "--no-deps", "ui-test")
    subprocess.run(["docker", "cp", "siteproof-integration-ui-proof:/tmp/dashboard.png", "evals/reports/stack/dashboard.png"], check=True)
    subprocess.run(["docker", "rm", "siteproof-integration-ui-proof"], check=True, capture_output=True)
    identifier = report["samples"][0]["job_id"]
    report["database_checks"] = compose("exec", "-T", "worker", "python", "evals/db_checks.py", "integration", identifier)
    request("DELETE", f"/api/jobs/{identifier}")
    assert httpx.get(API + f"/api/jobs/{identifier}", headers=HEADERS).status_code == 404
    report["deletion_checks"] = compose("exec", "-T", "worker", "python", "evals/deletion_checks.py", "integration", identifier)
    retrieval = compose("exec", "-T", "worker", "python", "evals/postgres_retrieval_run.py", "--tenant", "integration")
    Path("evals/reports/stack/retrieval.json").write_text(retrieval)
    report["checks"] = ["real axe/Lighthouse", "authenticated PNG retrieval", "idempotency", "worker kill/restart", "persisted correction", "duplicate delivery", "tenant denial", "UI images and evidence navigation", "job deletion"]
    Path("evals/reports/stack/report.json").write_text(json.dumps(report, indent=2))
    ranking = json.loads(retrieval)
    markdown = ["# Observed real-stack fixture integration", f"Completed fixture samples: {len(report['samples'])}."]
    markdown += [f"- {sample['slug']}: {sample['status']}; evidence={sample['evidence']}, findings={sample['findings']}, facts={sample['facts']}" for sample in report['samples']]
    markdown += ["\n## PostgreSQL retrieval", f"Corpus documents: {ranking['corpus_size']}; queries: {ranking['query_count']}."]
    markdown += [f"- {arm}: {values if values is not None else 'BLOCKED: real embeddings not configured'}" for arm, values in ranking['metrics'].items()]
    markdown += ["\n## Limits", "- Fixture audit results are not live AI results or client performance.",
                 "- Synthetic vectors test SQL mechanics only; no semantic vector/hybrid relevance measurement without credentials.",
                 "- No claim of production readiness or Phase 3 completion."]
    Path("evals/reports/stack/report.md").write_text("\n".join(markdown) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    Path("evals/reports/stack").mkdir(parents=True, exist_ok=True)
    main()
