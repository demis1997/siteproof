# Observed Phase 3–4 fixture validation

Mode: **fixture providers; real Docker/browser/database/storage**. Live AI quality, semantic retrieval and inference costs: **BLOCKED**.

Normal full pipeline: targeted repair and fact preservation passed (1 synthetic homepage). API test acceptance is not a human quality review.

Development labels: 1 TP, 0 FP, 0 FN categories across 3 pages; two supported viewport findings on the positive page. Labels are coding-agent authored, not independent human labels.

Controlled fault checks: initial regression rejected; one layout repair passed; persistent overflow stopped after two repairs; failed acceptance returned HTTP 409. Duplicate delivery created no additional evidence.

Fixture load: 3/3 completed; queue-inclusive p50 88.18s, p95 130.27s. Three observations, one worker, browser/domain limit one; not scalability or inference throughput.

Redesign worker restart: PASS. UI browser checks: PASS.

Each viewport has two real Lighthouse measurements before and after plus axe/DOM checks. Scores are diagnostic; no WCAG-compliance or conversion claims.

Original held-out labels retained unchanged. Nine-page contract evaluation is distinct from real browser grading and cannot measure model quality. A/B live baselines remain blocked; repair metrics are not applicable to audit-only arms.

Paid ledger: USD 2 reserved, USD 3.6345 unallocated under the existing ceiling. Actual failed-request cost remains unknown. OpenAI zero balance prevents live validation; no further paid request or retry was made.

Source provenance: local runs include working-tree changes on the recorded base commit. Final GitHub CI artifacts carry the committed revision. See JSON for sample sizes, artifacts, hardware and limitations.
