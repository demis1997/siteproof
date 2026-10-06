from contextlib import contextmanager

import pytest
from siteproof import journal
from siteproof.config import settings
from siteproof.security import test_fixture_url as fixture_allowed
from siteproof.security import validate_url


@pytest.mark.parametrize("mode,enabled,url,allowed", [
    ("fixture", True, "http://fixture.siteproof.test/clean", True),
    ("live", True, "http://fixture.siteproof.test/clean", False),
    ("fixture", False, "http://fixture.siteproof.test/clean", False),
    ("fixture", True, "http://fixture.siteproof.test.evil/clean", False),
    ("fixture", True, "http://user@fixture.siteproof.test/clean", False),
    ("fixture", True, "http://127.0.0.1/clean", False),
])
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
