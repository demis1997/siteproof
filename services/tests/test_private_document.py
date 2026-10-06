import httpx
from siteproof.preview_capture import private_document


def test_private_lighthouse_capability_and_cleanup():
    with private_document("<h1>Protected document</h1>") as url:
        response = httpx.get(url, trust_env=False)
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex,nofollow"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert httpx.get(url.rsplit("/", 1)[0] + "/wrong", trust_env=False).status_code == 403
    try:
        httpx.get(url, trust_env=False, timeout=1)
    except httpx.ConnectError:
        pass
    else:
        raise AssertionError("Preview document server survived cleanup")


def test_no_document_does_not_start_server():
    with private_document(None) as url:
        assert url is None


def test_repeated_lighthouse_is_required_for_workflow_verification():
    from siteproof.audit import REQUIRED_CHECKS, VIEWPORTS, verify
    from siteproof.contracts import PageSpec
    page = PageSpec(title='Test', headline='Test', about='', services=[], contacts=[], fixture=True).model_dump()
    checks = [{'id': name+'-'+v, 'kind': 'check', 'name': name, 'viewport': v, 'passed': True} for name in REQUIRED_CHECKS for v in VIEWPORTS]
    assert not verify([], checks, checks, [], page, require_lighthouse=True)['required_checks_passed']
    measured = checks + [{'id': 'lh-'+v, 'kind': 'lighthouse', 'viewport': v, 'sample_count': 2, 'median_scores': {'performance': 0.8}} for v in VIEWPORTS]
    assert verify([], measured, measured, [], page, require_lighthouse=True)['required_checks_passed']
