"""Observed contract evaluation. Browser/model benchmarks stay unavailable until run."""

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
from siteproof.audit import REQUIRED_CHECKS, VIEWPORTS, audit_evidence, verify
from siteproof.contracts import PageSpec, preserve_facts


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.inputs = []
        self.labels = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self.links.append(a.get("href", ""))
        if tag == "input":
            self.inputs.append(a)
        if tag == "label":
            self.labels.append(a.get("for"))


def source_checks(html, name):
    p = Elements()
    p.feed(html)
    import re

    checks = {
        "contact_links": all(
            bool(re.fullmatch("tel:\\+?[\\d ()-]+", x))
            if x.startswith("tel:")
            else bool(re.fullmatch("mailto:[^@\\s]+@[^@\\s]+\\.[^@\\s]+", x))
            for x in p.links
            if x.startswith(("tel:", "mailto:"))
        ),
        "accessible_labels": all(x.get("id") in p.labels or x.get("aria-label") for x in p.inputs),
    }
    return [
        {
            "id": f"{name}-{key}",
            "kind": "check",
            "name": key,
            "passed": value,
            "viewport": "source",
            "description": f"Static HTML {key} check",
        }
        for key, value in checks.items()
    ]


def run(out):
    labels = json.loads((ROOT / "evals/labels.json").read_text())
    rows = []
    durations = []
    tp = fp = fn = supported = total = 0
    for fixture in labels["fixtures"]:
        start = time.perf_counter()
        name = fixture["id"]
        evidence = source_checks((ROOT / f"evals/fixtures/{name}.html").read_text(), name)
        findings = audit_evidence(evidence)
        expected = set()
        if "invalid_phone_link" in fixture["objective_labels"] or "invalid_email_link" in fixture["objective_labels"]:
            expected.add("contact_links")
        if "missing_accessible_label" in fixture["objective_labels"]:
            expected.add("accessible_labels")
        predicted = {f["category"] for f in findings}
        tp += len(expected & predicted)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        supported += sum(set(f["evidence_ids"]) <= {e["id"] for e in evidence} for f in findings)
        total += len(findings)
        elapsed = time.perf_counter() - start
        durations.append(elapsed)
        rows.append(
            {
                "fixture": name,
                "observed_checks": evidence,
                "finding_ids": [f["id"] for f in findings],
                "expected_source_categories": sorted(expected),
                "latency_seconds": elapsed,
            }
        )
    facts = [
        {"kind": "phone", "value": "+1 202 555 0123", "href": "tel:+12025550123"},
        {"kind": "email", "value": "hello@example.test", "href": "mailto:hello@example.test"},
    ]
    spec = PageSpec(
        title="Harbor",
        headline="Plumbing",
        about="Local service",
        services=["Leak repairs"],
        contacts=facts,
        fixture=True,
    ).model_dump()
    before = [{"id": "before", "kind": "check", "name": "render", "passed": True, "viewport": "desktop"}]
    after = [{"id": "after", "kind": "check", "name": "render", "passed": False, "viewport": "desktop"}]
    regression = verify([], before, after, facts, spec)
    assert regression["regressions"] == ["after"] and regression["required_checks_passed"] is False
    missing_gate = verify([], [], [], facts, spec)
    assert missing_gate["required_checks_passed"] is False and len(missing_gate["missing_checks"]) == 14
    complete_checks = [
        {"id": f"{name}-{viewport}", "kind": "check", "name": name, "viewport": viewport, "passed": True}
        for viewport in VIEWPORTS
        for name in REQUIRED_CHECKS
    ]
    assert verify([], [], complete_checks, facts, spec)["required_checks_passed"] is False
    # Explicit controlled DOM inputs test a contract; these are not browser measurements.
    complete_checks += [
        {
            "id": f"controlled-dom-{viewport}",
            "kind": "dom",
            "viewport": viewport,
            "data": {"links": [{"text": fact["value"], "href": fact["href"]} for fact in facts], "text": ""},
        }
        for viewport in VIEWPORTS
    ]
    assert verify([], [], complete_checks, facts, spec)["required_checks_passed"] is True
    hypothesis = {"id": "subjective", "kind": "design_hypothesis", "verification_method": "render"}
    subjective = verify([hypothesis], [], complete_checks, facts, spec)
    assert subjective["results"][0]["status"] == "unverified"
    modified = dict(spec, contacts=[])
    try:
        preserve_facts(PageSpec.model_validate(modified), facts)
    except ValueError:
        fact_rejection = True
    else:
        fact_rejection = False
    assert fact_rejection
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": "contract-eval-v1",
        "python": platform.python_version(),
        "sample_size": len(rows),
        "scope": "Static HTML contact/label extraction and actual deterministic auditor/verification contracts; not browser or model quality.",
        "comparisons": {
            "A_single_prompt": {
                "status": "not_run",
                "reason": "Requires configured live model and controlled prompt experiment",
            },
            "B_rag_auditor": {"status": "not_run", "reason": "Requires database retrieval and configured live model"},
            "C_full_workflow": {
                "status": "not_run",
                "reason": "This harness evaluates contracts only; separate E2E/browser test required",
            },
        },
        "metrics": {
            "source_finding_precision": tp / (tp + fp) if tp + fp else None,
            "source_finding_recall": tp / (tp + fn) if tp + fn else None,
            "evidence_support_rate": supported / total if total else None,
            "source_finding_count": total,
            "regression_rejection": True,
            "missing_checks_rejection": True,
            "missing_rendered_fact_evidence_rejection": True,
            "complete_checks_contract_acceptance": True,
            "hypothesis_remains_unverified": True,
            "contact_fact_mutation_rejection": fact_rejection,
            "p50_contract_latency_seconds": statistics.median(durations),
            "p95_contract_latency_seconds": sorted(durations)[min(len(durations) - 1, int(0.95 * len(durations)))],
            "retrieval_recall_at_k": None,
            "targeted_browser_repair_success": None,
            "new_browser_regression_rate": None,
            "workflow_recovery_rate": None,
            "cost_per_accepted_preview": None,
        },
        "rows": rows,
        "limitations": [
            "Labels are source-inspected, not independently browser/human verified.",
            "Nine related variants from one synthetic business; no client generalization.",
            "Overflow, geometry, navigation semantics, timeout and partial capture need browser tests.",
            "A/B/C quality comparison, embeddings, live providers and actual accepted-preview cost were not measured.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    text = [
        "# Observed contract evaluation",
        f"\nGenerated {report['generated_at']}. Samples: {len(rows)}.",
        "\n" + report["scope"],
        "\n## Observed metrics",
    ]
    text += [f"- {k}: {(v if v is not None else 'unavailable')}" for k, v in report["metrics"].items()]
    text += ["\n## Baseline comparison"] + [
        f"- {k}: {v['status']} — {v['reason']}" for k, v in report["comparisons"].items()
    ]
    text += ["\n## Limitations"] + ["- " + s for s in report["limitations"]]
    (out / "report.md").write_text("\n".join(text) + "\n")
    print(json.dumps({"sample_size": len(rows), "metrics": report["metrics"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=ROOT / "evals/reports")
    a = p.parse_args()
    run(a.output)
