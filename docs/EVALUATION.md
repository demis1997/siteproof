# Evaluation methodology

Run the deterministic harness from the repository root using the command in README. JSON and Markdown reports are generated from observed execution, never target values. A missing capability has a null metric and an explicit limitation. Fixture performance is not client performance.

`evals/fixtures` contains authored service-business pages: clean control, mobile overflow, malformed contact links, missing form labels, weak navigation, conflicting facts, prompt injection, unavailable asset, and slow response. `labels.json` records source-inspected labels and their verification status. Browser confirmation is required before describing these as browser-validated human labels. `serve_fixtures.py` injects timeout and HTTP 503 behavior. Production URL validation must continue to reject loopback; use only a separately trusted test entry point.

All variants belong to one website group and the test split. Do not tune on these variants and report held-out performance. Add independent business groups before train/development/test comparisons. Related pages and variants must remain together to avoid leakage.

Compare A, a single structured prompt without retrieval; B, the same auditor with retrieved guidance; and C, the full redesign and executable verification loop. In fixture mode these are deterministic implementation smoke checks, not real model quality benchmarks. Live comparisons require recorded model IDs, prompt versions, matched inputs and budgets. Do not invent A/B results when only C runs.

Objective graders compare supported findings against labelled categories, validate every evidence reference, compare critical facts, and detect newly failed checks. Report precision, recall, support rate, retrieval recall@k and reciprocal rank, repair success, regression rate, completion/recovery, latency p50/p95, and cost per accepted preview only where the corresponding measurements exist. Unknown price remains unknown. Tiny sample sizes and deterministic provider behavior must be stated.

Human rubric: score message accuracy, fact fidelity, visual hierarchy, keyboard usability, contact discoverability, and business specificity from 1 (poor) to 5 (strong). Record reviewer, viewport, rationale, and evidence. Two independent reviewers should adjudicate disagreements. No human ratings have been collected for the initial fixtures. LLM judges are supplementary and require calibration against these ratings.

## Real browser slice

With the web service running, a real installed Chrome executable, and `npm ci --prefix infra` completed, run:

```sh
python evals/browser_run.py --web http://127.0.0.1:3000 --render-key local-render-key --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

The harness calls the actual capture service implementation with explicit trusted-fixture dependency injection, calls the application's authenticated `/internal/render` React renderer, captures the returned HTML at both production viewports, and runs the same auditor and verification gate. It stores real screenshots and evidence only after successful capture. Seven ordinary variants are tested; timeout and partial asset cases use actual browser interception with a neverfulfilled request and HTTP 503 respectively. This is a browser slice, not a database/queue/checkpoint end-to-end run.

The initial execution was attempted with both installed Chrome and Chromium headless shell. Both were blocked by the execution host sandbox; Chromium reported `MachPortRendezvousServer: Permission denied (1100)`. `evals/reports/browser/failure.json` records zero completed samples and null metrics. No browser screenshots, fixes, fault-probe outcomes, or accepted-preview performance were observed during this failed run. Run the command outside that restrictive host boundary or in the intended isolated container before treating browser behavior as verified.

## Independent local retrieval smoke evaluation

Run `python evals/retrieval_run.py` to rank the actual four-document guidance corpus using token overlap independently over titles and body text, then invoke the application's reciprocal rank fusion. Four authored query/relevance pairs measure observed recall@1, recall@3 and reciprocal rank. The report also checks duplicate rank-entry invariance. These intentionally simple local measurements are not PostgreSQL full-text, vector, tenant-isolation, reranker, or held-out model benchmarks; those metrics remain unavailable in this report. This evaluator does not open a database connection.

Contract acceptance inputs explicitly include synthetic DOM records at both viewports. They verify the acceptance gate, not browser-derived evidence. Missing DOM evidence for nonempty business facts must reject acceptance. Browser repair expectations now include destinations reconstructed only from valid captured displayed contact text, preserving that exact value and original destination provenance.
