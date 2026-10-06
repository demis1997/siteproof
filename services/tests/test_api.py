from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from siteproof import api


@pytest.fixture
def client(monkeypatch):
    rows = {}

    class Cursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

        def fetchall(self):
            return self.value

    class Conn:
        def execute(self, sql, args=()):
            if sql.startswith("SELECT * FROM audit_jobs WHERE id="):
                identifier, tenant = args
                row = rows.get(identifier)
                return Cursor(row if row and row["tenant_id"] == tenant else None)
            if sql.startswith("SELECT * FROM audit_jobs WHERE tenant_id"):
                tenant, key = args
                return Cursor(
                    next((r for r in rows.values() if r["tenant_id"] == tenant and r["idempotency_key"] == key), None)
                )
            if sql.startswith("INSERT INTO audit_jobs"):
                identifier, tenant, key, submitted, canonical, data = args
                existing = next(
                    (r for r in rows.values() if r["tenant_id"] == tenant and r["idempotency_key"] == key), None
                )
                if existing:
                    return Cursor(None)
                rows[identifier] = {
                    "id": identifier,
                    "tenant_id": tenant,
                    "idempotency_key": key,
                    "submitted_url": submitted,
                    "canonical_url": canonical,
                    "status": "queued",
                    "stage": "queued",
                    "data": data.obj,
                }
                return Cursor(rows[identifier])
            if sql.startswith("INSERT INTO task_outbox"):
                return Cursor(None)
            raise AssertionError(sql)

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr(api.db, "connection", connection)
    monkeypatch.setattr(
        api.db,
        "get_job",
        lambda tenant, identifier: (
            rows.get(identifier) if rows.get(identifier, {}).get("tenant_id") == tenant else None
        ),
    )
    monkeypatch.setattr(api, "enqueue", lambda *a, **kw: None)
    return TestClient(api.app), rows


def test_idempotency_and_conflict(client):
    http, rows = client
    headers = {"X-Tenant-Key": "local-development-key", "Idempotency-Key": "same"}
    first = http.post("/api/jobs", json={"url": "https://fixture.siteproof.test/clean"}, headers=headers)
    second = http.post("/api/jobs", json={"url": "https://fixture.siteproof.test/clean"}, headers=headers)
    assert first.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert len(rows) == 1
    conflict = http.post("/api/jobs", json={"url": "https://fixture.siteproof.test/overflow"}, headers=headers)
    assert conflict.status_code == 409


def test_auth_and_tenant_isolation(client):
    http, rows = client
    assert http.get("/api/jobs").status_code == 401
    rows["foreign"] = {"id": "foreign", "tenant_id": "other"}
    assert http.get("/api/jobs/foreign", headers={"X-Tenant-Key": "local-development-key"}).status_code == 404


def test_failure_prevents_acceptance(client, monkeypatch):
    http, rows = client
    rows["job"] = {"id": "job", "tenant_id": "local", "status": "needs_review"}
    monkeypatch.setattr(api.db, "records", lambda *a: [{"required_checks_passed": False}])
    response = http.post(
        "/api/jobs/job/review", json={"decision": "accept"}, headers={"X-Tenant-Key": "local-development-key"}
    )
    assert response.status_code == 409


def test_real_key_other_tenant_is_denied(client, monkeypatch):
    from siteproof.config import settings

    http, rows = client
    monkeypatch.setattr(settings, "tenant_keys_json", '{"local":"local-development-key","other":"other-key"}')
    rows["local-only"] = {"id": "local-only", "tenant_id": "local"}
    assert http.get("/api/jobs/local-only", headers={"X-Tenant-Key": "other-key"}).status_code == 404


def test_same_url_different_goal_conflicts(client):
    http, _ = client
    headers = {"X-Tenant-Key": "local-development-key", "Idempotency-Key": "goal"}
    assert (
        http.post(
            "/api/jobs", json={"url": "https://fixture.siteproof.test/clean", "goal": "first"}, headers=headers
        ).status_code
        == 201
    )
    assert (
        http.post(
            "/api/jobs", json={"url": "https://fixture.siteproof.test/clean", "goal": "second"}, headers=headers
        ).status_code
        == 409
    )
