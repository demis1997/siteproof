import pytest
from siteproof.audit import REQUIRED_CHECKS, VIEWPORTS, verify
from siteproof.contracts import PageSpec


def spec():
    return PageSpec(
        title="Fixture business", headline="Fixture business", about="", services=[], contacts=[], fixture=True
    ).model_dump()


def checks():
    return [
        {"id": f"{name}-{viewport}", "kind": "check", "name": name, "viewport": viewport, "passed": True}
        for viewport in VIEWPORTS
        for name in REQUIRED_CHECKS
    ]


@pytest.mark.parametrize("missing", range(14))
def test_every_required_viewport_check_must_exist(missing):
    evidence = checks()
    evidence.pop(missing)
    result = verify([], [], evidence, [], spec())
    assert not result["required_checks_passed"]
    assert len(result["missing_checks"]) == 1


def test_complete_check_set_is_necessary_and_sufficient_without_findings():
    assert verify([], [], checks(), [], spec())["required_checks_passed"]


def test_opinion_cannot_fix_a_failed_measurement():
    after = checks()
    after[0]["passed"] = False
    finding = {"id": "f", "kind": "objective_defect", "verification_method": "render"}
    result = verify([finding], checks(), after, [], spec())
    assert not result["required_checks_passed"]
    assert result["results"][0]["status"] == "regressed"
    assert result["regressions"] == ["render-desktop"]


def test_duplicate_success_cannot_hide_failure():
    after = checks()
    after.append(dict(after[0], id="duplicate", passed=False))
    assert not verify([], [], after, [], spec())["required_checks_passed"]


def test_hypotheses_remain_unverified_even_when_checks_pass():
    result = verify(
        [{"id": "hypothesis", "kind": "design_hypothesis", "verification_method": "contact_visible"}],
        [],
        checks(),
        [],
        spec(),
    )
    assert result["results"][0]["status"] == "unverified"


def test_displayed_phone_cannot_point_to_another_valid_number():
    from siteproof.contracts import preserve_facts

    page = PageSpec(
        title="Business",
        headline="Business",
        about="",
        services=[],
        fixture=True,
        contacts=[{"kind": "phone", "value": "+1 202 555 0123", "href": "tel:+12025559999"}],
    )
    with pytest.raises(ValueError, match="destination"):
        preserve_facts(page, [{"kind": "phone", "value": "+1 202 555 0123", "href": "tel:+12025550123"}])


def test_phone_in_service_copy_does_not_replace_contact():
    from siteproof.contracts import preserve_facts

    page = PageSpec(
        title="Business", headline="Business", about="", services=["+12025550123"], contacts=[], fixture=True
    )
    with pytest.raises(ValueError, match="omitted"):
        preserve_facts(page, [{"kind": "phone", "value": "+12025550123"}])


def test_repair_loop_stops_after_two_repairs_and_requests_review(monkeypatch):
    import time

    from siteproof import workflow

    calls = {"capture": 0, "render": 0}
    statuses = []
    monkeypatch.setattr(workflow.db, "get_job", lambda *args: {"status": "verifying"})
    monkeypatch.setattr(workflow.db, "update_job", lambda t, j, status, *args, **kwargs: statuses.append(status))
    monkeypatch.setattr(workflow.db, "save_records", lambda *args: None)
    monkeypatch.setattr(workflow, "once", lambda t, j, step, operation, **kwargs: operation())

    def capture(state, **kwargs):
        calls["capture"] += 1
        evidence = checks()
        for item in evidence:
            if item["name"] == "horizontal_overflow":
                item["passed"] = False
        evidence += [{"id": "lh-"+v, "kind": "lighthouse", "viewport": v, "sample_count": 2} for v in VIEWPORTS]
        return {"evidence": evidence}

    def render(state):
        calls["render"] += 1
        state["html"] = "<html></html>"

    monkeypatch.setattr(workflow, "remote_capture", capture)
    monkeypatch.setattr(workflow, "render_spec", render)
    state = {
        "tenant": "tenant",
        "job_id": "job",
        "action": "redesign",
        "findings": [],
        "evidence": [{"id": "lh-"+v, "kind": "lighthouse", "viewport": v, "sample_count": 2} for v in VIEWPORTS],
        "facts": [],
        "spec": spec(),
        "html": "<html></html>",
        "budget": {},
        "started": time.time(),
    }
    result = workflow.verifier(state)
    assert calls == {"capture": 3, "render": 2}
    assert result["verification"]["repair_attempts"] == 2
    assert not result["verification"]["required_checks_passed"]
    assert statuses[-1] == "needs_review"
