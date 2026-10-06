import pytest
from siteproof.contracts import Budget, validate_findings
from siteproof.retrieval import reciprocal_rank_fusion
from siteproof.security import validate_url
from siteproof.workflow import build_graph


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://10.0.0.1",
        "http://192.168.0.1",
        "https://example.com:9000",
    ],
)
def test_blocks_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_url(url, resolve=False)


def test_all_dns_addresses_checked(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError):
        validate_url("https://example.com")


def test_nonexistent_evidence_rejected():
    finding = {
        "id": "f",
        "category": "layout",
        "severity": "serious",
        "claim": "overflow",
        "evidence_ids": ["invented"],
        "confidence": 1,
        "kind": "objective_defect",
        "proposed_change": "repair",
        "verification_method": "horizontal_overflow",
    }
    with pytest.raises(ValueError):
        validate_findings([finding], [])


def test_budgets():
    with pytest.raises(ValueError):
        Budget(max_tool_calls=1).consume(calls=2)
    with pytest.raises(ValueError):
        Budget(max_tokens=2).consume(tokens=3)
    with pytest.raises(ValueError):
        Budget(max_seconds=1).consume(elapsed=2)
    with pytest.raises(ValueError):
        Budget(max_cost=1).consume(cost=2)


def test_rrf_deduplicates():
    assert reciprocal_rank_fusion([[{"id": "a"}, {"id": "b"}], [{"id": "b"}]]) == ["b", "a"]


def test_graph_is_bounded():
    graph = build_graph().get_graph()
    assert set(graph.nodes) == {"__start__", "auditor", "designer", "verifier", "__end__"}


def test_checkpoint_resume_does_not_repeat_successful_auditor(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    from siteproof import workflow

    calls = {"auditor": 0, "designer": 0, "verifier": 0}

    def auditor(state):
        calls["auditor"] += 1
        return {"findings": [{"id": "observed"}]}

    def designer(state):
        calls["designer"] += 1
        if calls["designer"] == 1:
            raise ConnectionError("simulated worker interruption after completed audit checkpoint")
        assert state["findings"][0]["id"] == "observed"
        return {"spec": {}}

    def verifier(state):
        calls["verifier"] += 1
        return {"verification": {"required_checks_passed": True}}

    monkeypatch.setattr(workflow, "auditor", auditor)
    monkeypatch.setattr(workflow, "designer", designer)
    monkeypatch.setattr(workflow, "verifier", verifier)
    graph = workflow.build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "tenant:job"}}
    with pytest.raises(ConnectionError):
        graph.invoke({"tenant": "tenant", "job_id": "job", "action": "redesign"}, config)
    assert graph.get_state(config).next == ("designer",)
    graph.invoke(None, config)
    assert calls == {"auditor": 1, "designer": 2, "verifier": 1}
    assert graph.get_state(config).values["verification"]["required_checks_passed"]


@pytest.mark.parametrize(
    "url",
    [
        "http://224.0.0.1/",
        "http://[ff02::1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[2002:7f00:1::]/",
        "https://example.com/\r\nHost: localhost",
    ],
)
def test_special_public_classifications_cannot_bypass_egress(url):
    with pytest.raises(ValueError):
        validate_url(url, resolve=False)


def test_budget_usage_cannot_be_refunded_by_negative_measurements():
    with pytest.raises(ValueError, match="negative"):
        Budget(tokens=100).consume(tokens=-100)
    with pytest.raises(ValueError, match="negative"):
        Budget(cost=1).consume(cost=-1)


@pytest.mark.parametrize(
    "url", ["http://@example.com", "http://:@example.com", "https://example.com:80", "http://example.com:443"]
)
def test_empty_credentials_and_mismatched_ports_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url, resolve=False)


def test_phone_validation_requires_digits_not_punctuation():
    from siteproof.security import valid_phone

    assert valid_phone("+1 (202) 555-0123")
    assert not valid_phone("-------")
    assert not valid_phone("123")
    assert not valid_phone("+1234567890123456")
