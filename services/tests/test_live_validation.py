"""Simulated provider transport/failure tests; never live-model observations."""

import base64
import hashlib
import json
import math
import sys
from pathlib import Path

import httpx
import pytest
from siteproof.config import settings
from siteproof.contracts import Budget
from siteproof.providers import LiveProvider

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals"))
from live_audit_run import inspect_findings
from semantic_retrieval_run import scores


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "model_key", "simulated-chat-key")
    monkeypatch.setattr(settings, "embedding_key", "simulated-embedding-key")
    monkeypatch.setattr(settings, "embedding_use_model_credentials", False)
    monkeypatch.setattr(settings, "embedding_url", "https://embedding.example/v1")
    monkeypatch.setattr(settings, "require_known_prices", False)
    for name in ("input_cost_per_million", "output_cost_per_million", "embedding_cost_per_million"):
        monkeypatch.setattr(settings, name, None)


def transport(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))


def chat_response(content=None, **overrides):
    result = {
        "model": settings.model_id,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps({"findings": []}) if content is None else content},
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    result.update(overrides)
    return result


def test_unknown_price_does_not_become_zero(setup, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json=chat_response()))
    _, run = LiveProvider().findings([], [], budget=Budget(max_cost=None))
    assert run["cost"] is None and run["cost_basis"] == "unknown"
    budget = Budget(max_cost=None)
    budget.consume(tokens=110, cost=run["cost"])
    budget.consume(tokens=1, cost=0.01)
    assert budget.cost is None and budget.cost_unknown


def test_unknown_price_with_explicit_money_budget_fails_before_transport(setup, monkeypatch):
    transport(monkeypatch, lambda request: pytest.fail("Paid call before price gate"))
    with pytest.raises(ValueError, match="Known prices"):
        LiveProvider().findings([], [], budget=Budget(max_cost=1))


def test_embedding_uses_separate_endpoint_and_credential(setup, monkeypatch):
    def handler(request):
        assert str(request.url) == "https://embedding.example/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer simulated-embedding-key"
        body = json.loads(request.content)
        assert body["dimensions"] == 1536
        return httpx.Response(
            200,
            json={
                "model": settings.embedding_model,
                "usage": {"total_tokens": 3},
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1535}],
            },
        )

    transport(monkeypatch, handler)
    model = LiveProvider(require_chat=False)
    assert len(model.embeddings(["text"], Budget(max_cost=None))[0]) == 1536
    assert model.last_embedding_run["cost"] is None


def test_no_implicit_embedding_credential_reuse(setup, monkeypatch):
    monkeypatch.setattr(settings, "embedding_key", "")
    with pytest.raises(ValueError, match="EMBEDDING_KEY"):
        LiveProvider().embeddings(["text"], Budget(max_cost=None))
    monkeypatch.setattr(settings, "embedding_use_model_credentials", True)
    assert settings.embedding_credential() == settings.model_key


def test_screenshot_request_contains_exact_bytes_and_byte_hash(setup, monkeypatch):
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5WQAAAAASUVORK5CYII="
    )
    encoded = base64.b64encode(png).decode()

    def handler(request):
        parts = json.loads(request.content)["messages"][1]["content"]
        sent = parts[1]["image_url"]["url"].split(",", 1)[1]
        assert base64.b64decode(sent) == png
        return httpx.Response(200, headers={"x-request-id": "simulated-request"}, json=chat_response())

    transport(monkeypatch, handler)
    _, run = LiveProvider().findings(
        [{"id": "shot", "kind": "screenshot"}], [], [{"id": "shot", "png": encoded}], Budget(max_cost=None)
    )
    assert run["images_sent"] == [{"id": "shot", "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest()}]
    assert run["provider_request_id"] == "simulated-request"


@pytest.mark.parametrize("code", [401, 429, 500])
def test_http_failures_never_substitute_fixture(setup, monkeypatch, code):
    transport(monkeypatch, lambda request: httpx.Response(code, json={"error": "simulated"}))
    with pytest.raises(httpx.HTTPStatusError):
        LiveProvider().findings([], [], budget=Budget(max_cost=None))


def test_timeout_never_substitutes_fixture(setup, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("simulated timeout", request=request)

    transport(monkeypatch, handler)
    with pytest.raises(httpx.ReadTimeout):
        LiveProvider().findings([], [], budget=Budget(max_cost=None))


@pytest.mark.parametrize(
    "response",
    [
        chat_response(content="not json"),
        chat_response(model="wrong-model"),
        chat_response(usage={}),
        chat_response(usage={"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0}),
    ],
)
def test_malformed_model_and_usage_rejected(setup, monkeypatch, response):
    transport(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises(ValueError):
        LiveProvider().findings([], [], budget=Budget(max_cost=None))


@pytest.mark.parametrize(
    "delta", [{"index": 1}, {"embedding": [1.0] * 3}, {"embedding": [float("nan")] + [0.0] * 1535}]
)
def test_invalid_embedding_shape_index_or_number(setup, monkeypatch, delta):
    payload = {
        "model": settings.embedding_model,
        "usage": {"total_tokens": 1},
        "data": [dict({"index": 0, "embedding": [1.0] * 1536}, **delta)],
    }
    if any(isinstance(x, float) and math.isnan(x) for x in payload["data"][0]["embedding"]):
        # JSON non-finite values simulated using permissive encoder, not a live provider.
        transport(monkeypatch, lambda request: httpx.Response(200, content=json.dumps(payload)))
    else:
        transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(ValueError):
        LiveProvider().embeddings(["text"], Budget(max_cost=None))


@pytest.mark.parametrize(
    "budget",
    [
        Budget(max_cost=None, max_tool_calls=0),
        Budget(max_cost=None, max_tokens=1),
        Budget(max_cost=None, max_seconds=1, elapsed_seconds=2),
    ],
)
def test_budget_exhaustion_prevents_transport(setup, monkeypatch, budget):
    transport(monkeypatch, lambda request: pytest.fail("Over-budget paid call"))
    with pytest.raises(ValueError):
        LiveProvider().findings([], [], budget=budget)


def test_no_answer_metrics_not_inflated_by_empty_relevance():
    assert scores(["a"], {}) is None
    result = scores(["b", "a"], {"a": 3, "b": 1})
    assert result["recall_at_3"] == 1 and result["mrr"] == 1 and 0 < result["ndcg_at_5"] < 1


def test_review_rejects_refs_and_keeps_hypotheses_uncertain():
    findings = [
        {
            "claim": "Unsupported",
            "kind": "objective_defect",
            "evidence_ids": ["missing"],
            "guidance_ids": [],
            "proposed_change": "Fix",
        },
        {
            "claim": "Review messaging",
            "kind": "design_hypothesis",
            "evidence_ids": ["dom"],
            "guidance_ids": ["source"],
            "proposed_change": "Review",
        },
    ]
    result = inspect_findings(findings, [{"id": "dom", "kind": "dom"}], [{"id": "source", "source": "local://sample"}])
    assert [row["support"] for row in result] == ["unsupported", "uncertain"]


def test_benchmark_labels_are_inspectable_and_split():
    root = Path(__file__).resolve().parents[2]
    corpus = json.loads((root / "knowledge/retrieval-benchmark-v1.json").read_text())
    data = json.loads((root / "evals/retrieval-dataset-v1.json").read_text())
    ids = {d["id"] for d in corpus["documents"]}
    assert len(ids) >= 15 and len(data["queries"]) >= 25
    assert all(set(q["relevance"]) <= ids and q["independent_review"] == "required" for q in data["queries"])
    assert {q["split"] for q in data["queries"]} == {"dev", "held_out"}
    assert any(q["no_answer"] for q in data["queries"])


def test_api_missing_chat_and_embedding_credentials_are_explicit(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from siteproof.api import app

    monkeypatch.setattr(settings, "tenant_keys_json", "")
    headers = {"X-Tenant-Key": settings.tenant_key, "Idempotency-Key": "configuration-test"}
    monkeypatch.setattr(settings, "model_key", "")
    client = TestClient(app)
    response = client.post("/api/jobs", headers=headers, json={"url": "https://example.com"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "credentials_missing"
    monkeypatch.setattr(settings, "model_key", "simulated-chat-key")
    monkeypatch.setattr(settings, "embedding_key", "")
    response = client.post("/api/jobs", headers=headers, json={"url": "https://example.com"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "embedding_credentials_missing"


def test_api_prices_required_only_for_explicit_policy(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from siteproof.api import app

    monkeypatch.setattr(settings, "tenant_keys_json", "")
    monkeypatch.setattr(settings, "require_known_prices", True)
    response = TestClient(app).post(
        "/api/jobs",
        headers={"X-Tenant-Key": settings.tenant_key, "Idempotency-Key": "price-test"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 503 and response.json()["detail"]["code"] == "pricing_missing"


def test_model_cannot_invent_a_score_or_unattributed_guidance(setup, monkeypatch):
    from siteproof.contracts import Finding

    raw = Finding(
        id="hypothesis",
        category="hierarchy",
        severity="minor",
        claim="Score improves to 90 points",
        evidence_ids=["dom"],
        guidance_ids=["source"],
        confidence=0.5,
        kind="design_hypothesis",
        proposed_change="Review",
        verification_method="human_review",
    ).model_dump()
    transport(
        monkeypatch, lambda request: httpx.Response(200, json=chat_response(content=json.dumps({"findings": [raw]})))
    )
    with pytest.raises(ValueError, match="Unsupported quantitative"):
        LiveProvider().findings([{"id": "dom", "kind": "dom"}], [{"id": "source"}], budget=Budget(max_cost=None))
    raw["claim"] = "Review hierarchy"
    raw["guidance_ids"] = []
    with pytest.raises(ValueError, match="guidance references"):
        LiveProvider().findings([{"id": "dom", "kind": "dom"}], [{"id": "source"}], budget=Budget(max_cost=None))
