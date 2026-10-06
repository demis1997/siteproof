"""Deterministic diagnosis and conservative acceptance; opinions cannot waive checks."""

from .contracts import PageSpec, preserve_facts, validate_findings

VIEWPORTS = ("desktop", "mobile")
REQUIRED_CHECKS = (
    "render",
    "horizontal_overflow",
    "contact_links",
    "contact_visible",
    "internal_links",
    "axe",
    "accessible_labels",
)


def audit_evidence(evidence: list[dict]) -> list[dict]:
    findings = []
    for item in evidence:
        if item["kind"] == "check" and item.get("passed") is False:
            findings.append(
                {
                    "id": "finding-" + item["id"],
                    "category": item["name"],
                    "severity": "serious",
                    "claim": item.get("description", item["name"].replace("_", " ") + " failed"),
                    "evidence_ids": [item["id"]],
                    "confidence": 1,
                    "kind": "objective_defect",
                    "proposed_change": "Repair " + item["name"].replace("_", " "),
                    "verification_method": item["name"],
                    "approved": False,
                }
            )
        if item["kind"] == "axe" and item.get("impact") in ("critical", "serious"):
            findings.append(
                {
                    "id": "finding-" + item["id"],
                    "category": "accessibility",
                    "severity": item["impact"],
                    "claim": item["description"],
                    "evidence_ids": [item["id"]],
                    "confidence": 1,
                    "kind": "objective_defect",
                    "proposed_change": item["help"],
                    "verification_method": "axe",
                    "approved": False,
                }
            )
    return validate_findings(findings, evidence)


def verify(findings, before, after, facts, spec, *, require_lighthouse=False):
    """Require every check at both viewports, and preserve human uncertainty."""
    results = []
    try:
        preserve_facts(PageSpec.model_validate(spec), facts)
        fact_ok = True
    except (ValueError, KeyError):
        fact_ok = False
    rendered_fact_checks = []
    if facts:
        import re
        from urllib.parse import unquote

        for viewport in VIEWPORTS:
            dom = next(
                (e.get("data", {}) for e in after if e.get("kind") == "dom" and e.get("viewport") == viewport), None
            )
            passed = dom is not None
            for fact in facts:
                if dom is None:
                    break
                kind, value = fact["kind"], fact["value"]
                if kind in ("phone", "email"):
                    expected = fact.get("href", ("tel:" if kind == "phone" else "mailto:") + value)
                    normalize = (lambda text: re.sub(r"[(). \-]", "", text)) if kind == "phone" else unquote
                    passed &= any(
                        value in link.get("text", "") and normalize(link.get("href") or "") == normalize(expected)
                        for link in dom.get("links", [])
                    )
                elif kind in ("service", "hours", "price"):
                    passed &= value in dom.get("text", "")
            rendered_fact_checks.append({"viewport": viewport, "passed": passed})
        fact_ok &= all(c["passed"] for c in rendered_fact_checks)
    check_index = {}
    for evidence in after:
        if evidence["kind"] == "check":
            check_index.setdefault((evidence.get("name"), evidence.get("viewport")), []).append(evidence)
    missing = [
        {"name": name, "viewport": viewport}
        for viewport in VIEWPORTS
        for name in REQUIRED_CHECKS
        if (name, viewport) not in check_index
    ]
    if require_lighthouse:
        for phase, measurements in [("before", before), ("after", after)]:
            for viewport in VIEWPORTS:
                if not any(e.get("kind") == "lighthouse" and e.get("viewport") == viewport and e.get("sample_count", 0) >= 2 for e in measurements):
                    missing.append({"name": "lighthouse", "viewport": viewport, "phase": phase})
    for finding in findings:
        method = finding["verification_method"]
        checks = [e for e in after if e["kind"] == "check" and e.get("name") == method]
        measured = {e.get("viewport") for e in checks}
        if finding["kind"] == "design_hypothesis" or not set(VIEWPORTS) <= measured:
            status = "unverified"
        else:
            status = "fixed" if all(e.get("passed") is True for e in checks) else "unresolved"
        results.append(
            {
                "id": "verification-" + finding["id"],
                "finding_id": finding["id"],
                "status": status,
                "evidence_ids": [e["id"] for e in checks],
                "method": method,
            }
        )
    regressions = []
    for check in after:
        if check["kind"] == "check" and check.get("passed") is False:
            original = [
                e
                for e in before
                if e["kind"] == "check"
                and e.get("name") == check.get("name")
                and e.get("viewport") == check.get("viewport")
            ]
            if original and all(e.get("passed") is True for e in original):
                regressions.append(check["id"])
    for result in results:
        if result["status"] != "unverified" and set(result["evidence_ids"]).intersection(regressions):
            result["status"] = "regressed"
    required = [
        e for e in after if e["kind"] == "check" and e.get("name") in REQUIRED_CHECKS and e.get("viewport") in VIEWPORTS
    ]
    objective_ids = {f["id"] for f in findings if f["kind"] == "objective_defect"}
    targets_fixed = all(r["status"] == "fixed" for r in results if r["finding_id"] in objective_ids)
    accepted = (
        not missing and fact_ok and not regressions and targets_fixed and all(e.get("passed") is True for e in required)
    )
    # Fixed targeted issues may also regress elsewhere; the acceptance gate still fails.
    return {
        "results": results,
        "regressions": regressions,
        "facts_preserved": fact_ok,
        "required_checks_passed": accepted,
        "missing_checks": missing,
        "rendered_fact_checks": rendered_fact_checks,
        "lighthouse_comparison": [{"viewport": viewport, "before": next((e.get("median_scores") for e in before if e.get("kind") == "lighthouse" and e.get("viewport") == viewport), None), "after": next((e.get("median_scores") for e in after if e.get("kind") == "lighthouse" and e.get("viewport") == viewport), None)} for viewport in VIEWPORTS],
        "limitations": [
            "Automated checks do not establish WCAG compliance or conversion impact.",
            "Design hypotheses require human or live-user validation.",
        ],
    }
