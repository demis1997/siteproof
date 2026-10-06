"""Real trusted-local browser slice; no arbitrary public URL or model benchmark."""

import argparse
import base64
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

import httpx
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright
from siteproof.audit import audit_evidence, verify
from siteproof.capture import VIEWPORTS, capture
from siteproof.contracts import PageSpec


def run(args):
    if not Path(args.axe).is_file():
        raise RuntimeError("Install infra npm dependencies; real axe runtime required")
    labels = json.loads((ROOT / "evals/labels.json").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    observations = []
    for fixture in labels["fixtures"]:
        name = fixture["id"]
        if name in ("timeout", "partial_capture"):
            continue
        started = time.monotonic()
        original = (ROOT / f"evals/fixtures/{name}.html").read_text()
        before = capture(html=original, proxy=None, executable_path=args.chrome, axe_path=args.axe)
        if not before["screenshots"]:
            raise RuntimeError(f"No real capture for {name}: {before['evidence']}")
        findings = audit_evidence(before["evidence"])
        categories = {finding["category"] for finding in findings}
        expected_categories = {
            "overflow": "horizontal_overflow",
            "broken_contact": "contact_links",
            "missing_labels": "accessible_labels",
        }
        if name in expected_categories:
            assert expected_categories[name] in categories, f"Expected defect not detected: {name}"
        dom = next(e["data"] for e in before["evidence"] if e["kind"] == "dom")
        headings = [h["text"] for h in dom["headings"] if h["text"]]
        facts = before["facts"]
        spec = PageSpec(
            title=dom["title"],
            headline=headings[0],
            about=" ".join(headings[1:3]),
            services=[f["value"] for f in facts if f["kind"] == "service"],
            details=[f["value"] for f in facts if f["kind"] in ("hours", "price")],
            contacts=[
                {"kind": f["kind"], "value": f["value"], "href": f["href"]}
                for f in facts
                if f["kind"] in ("email", "phone")
            ],
            fixture=True,
        )
        response = httpx.post(
            args.web + "/internal/render",
            headers={"X-Render-Key": args.render_key},
            json={"spec": spec.model_dump()},
            timeout=20,
        )
        response.raise_for_status()
        (args.output / f"{name}-preview.html").write_text(response.text)
        after = capture(html=response.text, proxy=None, executable_path=args.chrome, axe_path=args.axe)
        result = verify(findings, before["evidence"], after["evidence"], facts, spec.model_dump())
        assert result["facts_preserved"], f"Business facts changed: {name}"
        if name == "broken_contact":
            contact_results = [r for r in result["results"] if r["method"] == "contact_links"]
            assert contact_results and all(r["status"] == "fixed" for r in contact_results), (
                "Valid source-text contacts must repair malformed destinations"
            )
        if name in ("overflow", "missing_labels"):
            targeted = [r for r in result["results"] if r["method"] == expected_categories[name]]
            assert targeted and all(r["status"] == "fixed" for r in targeted), f"Targeted repair failed: {name}"
        for stage, data in [("before", before), ("after", after)]:
            for shot in data["screenshots"]:
                (args.output / f"{name}-{stage}-{shot['viewport']}.png").write_bytes(base64.b64decode(shot["png"]))
        observations.append(
            {
                "fixture": name,
                "latency_seconds": time.monotonic() - started,
                "before": before["evidence"],
                "after": after["evidence"],
                "findings": findings,
                "verification": result,
                "fact_count": len(facts),
                "renderer": "controlled-react-components-v1",
            }
        )
        print(
            json.dumps({"fixture": name, "passed": result["required_checks_passed"], "results": result["results"]}),
            flush=True,
        )
    # Real browser fault probes use intercepted local-only resources, never a public URL.
    faults = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome)
        for viewport, size in VIEWPORTS.items():
            page = browser.new_page(viewport=size)
            page.route("http://fixture.invalid/timeout", lambda route: None)
            started = time.monotonic()
            try:
                page.goto("http://fixture.invalid/timeout", timeout=250)
            except BrowserTimeout as exc:
                faults.append(
                    {
                        "case": "timeout",
                        "viewport": viewport,
                        "outcome": "unavailable",
                        "exception": type(exc).__name__,
                        "elapsed_seconds": time.monotonic() - started,
                    }
                )
            page.close()
            page = browser.new_page(viewport=size)
            page.route(
                "http://fixture.invalid/unavailable.png",
                lambda route: route.fulfill(status=503, body="fixture unavailable"),
            )
            partial = (
                (ROOT / "evals/fixtures/partial_capture.html")
                .read_text()
                .replace("/unavailable.png", "http://fixture.invalid/unavailable.png")
            )
            statuses = []
            page.on("response", lambda response, statuses=statuses: statuses.append(response.status))
            page.set_content(partial)
            unavailable = page.locator("img").evaluate("(e)=>e.complete && e.naturalWidth===0")
            assert unavailable and 503 in statuses
            faults.append(
                {
                    "case": "partial_asset",
                    "viewport": viewport,
                    "outcome": "unavailable",
                    "response_statuses": statuses,
                    "image_unavailable": unavailable,
                }
            )
            page.close()
        browser.close()
    assert all(x["outcome"] == "unavailable" for x in faults)
    results = [r for row in observations for r in row["verification"]["results"]]
    count = sum(x["status"] == "fixed" for x in results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": "browser-slice-v1",
        "sample_size": len(observations),
        "scope": "Actual local Chrome + axe capture, deterministic diagnosis, controlled React HTML rendering and verifier. No database, queue, checkpoint or live-model integration.",
        "metrics": {
            "fixed_targeted_findings": count,
            "targeted_finding_count": len(results),
            "targeted_repair_success": count / len(results) if results else None,
            "passed_preview_count": sum(row["verification"]["required_checks_passed"] for row in observations),
            "new_regression_count": sum(len(row["verification"]["regressions"]) for row in observations),
            "fault_probe_count": len(faults),
            "cost_per_accepted_preview": None,
        },
        "observations": observations,
        "fault_probes": faults,
        "limitations": [
            "Synthetic related fixtures; no real-client performance estimate.",
            "Lighthouse unavailable for HTML preview and not included in success metrics.",
            "No live AI A/B, RAG ranking, persisted workflow recovery or full Compose E2E measured.",
            "Contact destinations are repaired only from captured valid displayed contact values; no invented facts.",
            "Source labels are authored; no independent human subjective ratings.",
        ],
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    text = [
        "# Observed browser slice",
        f"\nGenerated {report['generated_at']}. Samples: {len(observations)}.",
        "\n" + report["scope"],
        "\n## Observed metrics",
    ]
    text += [f"- {k}: {v if v is not None else 'unknown'}" for k, v in report["metrics"].items()]
    text += ["\n## Limitations"] + ["- " + x for x in report["limitations"]]
    (args.output / "report.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    parser.add_argument("--render-key", default="local-render-key")
    parser.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--axe", default=str(ROOT / "infra/node_modules/axe-core/axe.min.js"))
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports/browser")
    args = parser.parse_args()
    try:
        run(args)
    except (BrowserError, httpx.HTTPError, RuntimeError, AssertionError) as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        failure = {
            "generated_at": datetime.now(UTC).isoformat(),
            "version": "browser-slice-v1",
            "status": "failed" if isinstance(exc, AssertionError) else "unavailable",
            "sample_size": 0,
            "error_type": type(exc).__name__,
            "reason": str(exc)[:3000],
            "metrics": None,
            "limitations": ["No browser repair success or E2E completion measured during this failed run."],
        }
        (args.output / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        (args.output / "failure.md").write_text(
            "# Browser evaluation unavailable\n\n"
            + type(exc).__name__
            + ": "
            + str(exc).splitlines()[0]
            + "\n\nNo successful browser benchmark measured.\n"
        )
        raise
