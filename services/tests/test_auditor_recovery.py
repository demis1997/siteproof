from contextlib import contextmanager

import pytest
from siteproof import journal
from siteproof.config import settings
from siteproof.security import test_fixture_url as fixture_allowed
from siteproof.security import validate_url


@pytest.mark.parametrize(
    "mode,enabled,url,allowed",
    [
        ("fixture", True, "http://fixture.siteproof.test/clean", True),
        ("live", True, "http://fixture.siteproof.test/clean", False),
        ("fixture", False, "http://fixture.siteproof.test/clean", False),
        ("fixture", True, "http://fixture.siteproof.test.evil/clean", False),
        ("fixture", True, "http://user@fixture.siteproof.test/clean", False),
        ("fixture", True, "http://127.0.0.1/clean", False),
    ],
)
def test_fixture_exception_is_narrow(monkeypatch, mode, enabled, url, allowed):
    monkeypatch.setattr(settings, "mode", mode)
    monkeypatch.setattr(settings, "test_fixture_http", enabled)
    assert fixture_allowed(url) is allowed


def test_fixture_config_does_not_allow_private_addresses(monkeypatch):
    monkeypatch.setattr(settings, "test_fixture_http", True)
    with pytest.raises(ValueError):
        validate_url("http://169.254.169.254/latest/meta-data")


def connection_for(monkeypatch, row):
    class Result:
        def fetchone(self):
            return row

    class Conn:
        def execute(self, *args):
            return Result()

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr(journal, "connection", connection)


def test_persisted_success_does_not_call_operation(monkeypatch):
    connection_for(monkeypatch, {"status": "succeeded", "result": {"tokens": 12}})
    assert journal.once("t", "j", "audit", lambda: pytest.fail("Repeated paid call"), paid=True) == {"tokens": 12}


def test_uncertain_paid_call_requires_review(monkeypatch):
    connection_for(monkeypatch, {"status": "started", "result": None})
    with pytest.raises(ValueError, match="Uncertain in-flight"):
        journal.once("t", "j", "audit", lambda: pytest.fail("Replayed uncertain call"), paid=True)


def test_embedding_identity_invalidates_endpoint_and_version(monkeypatch):
    from siteproof.retrieval import embedding_identity

    original = embedding_identity()
    monkeypatch.setattr(settings, "embedding_version", "new-version")
    revised = embedding_identity()
    assert revised != original
    monkeypatch.setattr(settings, "model_url", "https://different-provider.example/v1")
    assert embedding_identity() != revised


def stateful_connection(monkeypatch, *, fail_save=False):
    import httpx

    state = {"row": None, "fail_save": fail_save}

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Conn:
        def execute(self, sql, args):
            if sql.startswith("SELECT"):
                return Result(state["row"])
            if sql.startswith("INSERT"):
                state["row"] = {"status": "started", "result": None}
            elif sql.startswith("DELETE"):
                state["row"] = None
            elif sql.startswith("UPDATE"):
                if state["fail_save"]:
                    state["fail_save"] = False
                    raise httpx.TransportError("Simulated durable-save interruption")
                state["row"] = {"status": "succeeded", "result": args[0].obj}
            return Result()

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr(journal, "connection", connection)
    return state


def test_successful_result_replayed_without_duplicate_operation(monkeypatch):
    stateful_connection(monkeypatch)
    calls = []

    def operation():
        calls.append("remote")
        return {"findings": [{"id": "same"}], "tokens": 12}

    first = journal.once("t", "j", "audit", operation, paid=True)
    second = journal.once("t", "j", "audit", operation, paid=True)
    assert first == second and len(calls) == 1


def test_response_not_durably_saved_is_uncertain_on_resume(monkeypatch):
    import httpx

    stateful_connection(monkeypatch, fail_save=True)
    calls = []

    def operation():
        calls.append("remote")
        return {"tokens": 10}

    with pytest.raises(httpx.TransportError):
        journal.once("t", "j", "audit", operation, paid=True)
    with pytest.raises(ValueError, match="Uncertain"):
        journal.once("t", "j", "audit", operation, paid=True)
    assert len(calls) == 1


def test_timeout_leaves_uncertain_marker_and_no_replay(monkeypatch):
    import httpx

    stateful_connection(monkeypatch)
    calls = []

    def operation():
        calls.append("remote")
        raise httpx.ReadTimeout("Simulated timeout")

    with pytest.raises(httpx.ReadTimeout):
        journal.once("t", "j", "audit", operation, paid=True)
    with pytest.raises(ValueError, match="Uncertain"):
        journal.once("t", "j", "audit", operation, paid=True)
    assert len(calls) == 1


def test_explicit_rate_limit_rejection_can_retry(monkeypatch):
    import httpx

    state = stateful_connection(monkeypatch)
    request = httpx.Request("POST", "https://model.example/chat")

    def rejection():
        raise httpx.HTTPStatusError(
            "Simulated rejection", request=request, response=httpx.Response(429, request=request)
        )

    with pytest.raises(httpx.HTTPStatusError):
        journal.once("t", "j", "audit", rejection, paid=True)
    assert state["row"] is None
    assert journal.once("t", "j", "audit", lambda: {"tokens": 4}, paid=True) == {"tokens": 4}
