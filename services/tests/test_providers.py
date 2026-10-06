import json

import pytest
from siteproof.config import settings
from siteproof.contracts import Budget, Finding
from siteproof.providers import FindingsResponse, FixtureProvider, LiveProvider, provider, strict_schema


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "embedding_use_model_credentials", True)
    monkeypatch.setattr(settings, "model_key", "test-credential-not-live")
    monkeypatch.setattr(settings, "input_cost_per_million", 1.0)
    monkeypatch.setattr(settings, "output_cost_per_million", 2.0)
    monkeypatch.setattr(settings, "embedding_cost_per_million", 0.1)


def test_live_never_silently_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "model_key", "")
    with pytest.raises(ValueError, match="MODEL_KEY"):
        provider()


def test_live_requires_known_prices(configured, monkeypatch):
    monkeypatch.setattr(settings, "output_cost_per_million", None)
    monkeypatch.setattr(settings, "require_known_prices", True)
    with pytest.raises(ValueError, match="prices"):
        LiveProvider()


def test_preflight_money_gate_before_request(configured):
    with pytest.raises(ValueError, match="Money budget"):
        LiveProvider().findings([], [], budget=Budget(max_cost=0))


def test_preflight_token_gate_before_request(configured):
    with pytest.raises(ValueError, match="bounded model context"):
        LiveProvider().findings([], [], budget=Budget(max_tokens=1))


def test_fixture_cost_unknown_and_no_fake_embeddings():
    _, run = FixtureProvider().findings([], [])
    assert run["fixture"] and run["cost"] is None
    with pytest.raises(ValueError, match="no fabricated embeddings"):
        FixtureProvider().embeddings(["test"])


def test_strict_schema_closes_objects_and_requires_defaults():
    schema = strict_schema(FindingsResponse.model_json_schema())
    finding = schema["$defs"]["Finding"]
    assert finding["additionalProperties"] is False
    assert "approved" in finding["required"]
    assert "default" not in finding["properties"]["approved"]


def mock_chat(monkeypatch, finding):
    from siteproof import providers

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "model": settings.model_id,
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"findings": [finding]})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            assert kwargs["json"]["response_format"]["type"] == "json_schema"
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "Client", FakeClient)


def finding(evidence_id="real", kind="design_hypothesis"):
    return Finding(
        id="hypothesis",
        category="hierarchy",
        severity="minor",
        claim="Review clarity",
        evidence_ids=[evidence_id],
        confidence=0.5,
        kind=kind,
        proposed_change="Review",
        verification_method="human_review",
        approved=True,
    ).model_dump()


def test_model_self_approval_is_removed_and_cost_accounted(configured, monkeypatch):
    mock_chat(monkeypatch, finding())
    findings, run = LiveProvider().findings([{"id": "real", "kind": "dom"}], [])
    assert findings[0]["approved"] is False
    assert run["cost"] == pytest.approx(0.0002)
    assert run["tokens"] == 150


def test_model_cannot_cite_nonexistent_evidence(configured, monkeypatch):
    mock_chat(monkeypatch, finding("fabricated"))
    with pytest.raises(ValueError, match="nonexistent evidence"):
        LiveProvider().findings([{"id": "real", "kind": "dom"}], [])


def test_model_objective_defect_requires_measurement(configured, monkeypatch):
    mock_chat(monkeypatch, finding(kind="objective_defect"))
    with pytest.raises(ValueError, match="no executable defect"):
        LiveProvider().findings([{"id": "real", "kind": "dom"}], [])


def test_model_cannot_cite_nonexistent_guidance(configured, monkeypatch):
    raw = finding()
    raw["guidance_ids"] = ["invented-source"]
    mock_chat(monkeypatch, raw)
    with pytest.raises(ValueError, match="nonexistent guidance"):
        LiveProvider().findings([{"id": "real", "kind": "dom"}], [{"id": "real-source"}])


def test_hypothesis_cannot_invent_conversion_measurement(configured, monkeypatch):
    raw = finding()
    raw["claim"] = "This improves conversion by 20%"
    mock_chat(monkeypatch, raw)
    with pytest.raises(ValueError, match="Unsupported quantitative"):
        LiveProvider().findings([{"id": "real", "kind": "dom"}], [])
