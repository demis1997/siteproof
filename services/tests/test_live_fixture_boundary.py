import httpx
import pytest
from siteproof.config import settings
from siteproof.providers import provider_error_report
from siteproof.security import test_fixture_url as fixture_allowed
from siteproof.security import validate_url


def test_disabled_by_default():
    from siteproof.config import Settings
    assert Settings(_env_file=None).live_validation_fixture is False


@pytest.mark.parametrize("url", [
    "http://fixture.siteproof.test/overflow", "http://fixture.siteproof.test:80/overflow",
])
def test_live_fixture_exact_route(monkeypatch, url):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "live_validation_fixture", True)
    assert fixture_allowed(url)
    assert validate_url(url) == url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/overflow", "http://10.0.0.1/overflow",
    "http://169.254.169.254/overflow", "http://[::1]/overflow",
    "http://fixture.siteproof.test:8082/overflow", "https://fixture.siteproof.test/overflow",
    "http://fixture.siteproof.test/clean", "http://fixture.siteproof.test/overflow?target=localhost",
    "http://fixture.siteproof.test.evil/overflow", "http://user@fixture.siteproof.test/overflow",
])
def test_live_redirect_and_subrequest_destinations_blocked(monkeypatch, url):
    monkeypatch.setattr(settings, "mode", "live")
    monkeypatch.setattr(settings, "live_validation_fixture", True)
    assert not fixture_allowed(url)
    # The same validator is used for submission, redirects and every browser request.
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize("code", ["insufficient_quota", "rate_limit_exceeded", "invalid_api_key", "secret-code", []])
def test_safe_provider_error_classification(code):
    response = httpx.Response(429, json={"error": {"code": code, "message": "SECRET API KEY CONTENT"}})
    report = provider_error_report(response)
    assert "SECRET" not in str(report)
    assert report["error_code"] == (None if code in ("secret-code", []) else code)
    assert report["automatic_retry"] is False
