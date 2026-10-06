# Phases 3–4: fixture implementation and observed validation

All current runs use explicitly labelled deterministic fixture providers and real Docker services. OpenAI balance is zero: **live model quality, semantic retrieval and actual inference costs are BLOCKED**. There are no paid retries. The private root `.env` remains live; the separate `siteproof-integration` project overrides fixture mode and clears provider credentials. Existing live jobs and volumes are retained, not converted.

## Reproduce locally

From the repository root, with Docker running and the documented Python environment installed:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.integration.yaml --profile integration -p siteproof-integration up -d --build
python evals/stack_run.py
python evals/phase34_run.py
python evals/regression_gate.py
python evals/phase34_recovery.py
python evals/phase34_ui_run.py
python evals/write_phase34_report.py
python evals/run.py
```

The integration dashboard is http://localhost:3000; use the intentionally public local test credential `integration-key`. Do not expose this profile to the internet. Normal and integration projects use the same host ports: stop the normal project first, without `-v`. Reports live under `evals/reports/phase34`. Test approval and acceptance actions exercise API controls; they are not independent human design judgments.

## Implementation and security boundaries

The Designer produces a validated component specification, never arbitrary code. The renderer permits three layouts and two typography choices, preserves approved contact/service facts, and includes no external scripts or tracking. Live Designer code accepts original screenshot bytes, guidance and approved findings; its live quality is untested. Model calls are journalled with conservative budgets; ambiguous remote execution is not claimed exactly once.

The Verifier uses executable evidence. Both viewports need successful rendering, required objective checks and two Lighthouse samples. Each repair has immutable verification and redesign records; at most two deterministic layout repairs are attempted. A passing check still requires explicit human acceptance. A failed check cannot be waived by the Verifier or acceptance API.

Private Lighthouse uses an ephemeral, unguessable document capability on browser-container loopback. It serves only trusted renderer HTML (or the already captured controlled fixture document), has no host port, denies other paths, emits noindex/CSP/no-store, and is destroyed after measurement. Submitted URLs and subrequests retain the restricted proxy/SSRF policy. It grants no arbitrary private-network browsing. Controlled before/after fixtures use the same document-serving measurement conditions. Public-site network performance and isolated preview performance are not equivalent environments; scores are diagnostics, never conversion evidence or WCAG certification.

## Dataset and grading

`phase34-dataset-v1.json` keeps related website variants together. Maple Cleaning and Cedar Electric are development groups. Original Harbor fixtures and `evals/labels.json` remain unchanged and held out for this new development set; hashes and group boundaries are tested. These are synthetic businesses with agent-authored, source-inspected objective labels, pending independent human review. They cannot establish real-client performance. Harbor fixtures were used during earlier milestones, so this preserved historical test group is not a never-seen independent hold-out. No labels or split memberships were tuned against the current results.

The development report measures category-level TP/FP/FN, not individual defect recall. Evidence support checks actual referenced IDs. Pipeline grades preservation of approved facts and executable repair outcomes. Fault scenarios deliberately inject CSS overflow at the trusted renderer boundary, use real browser/DB/checkpoints/storage, and test rejection and repair exhaustion. They do not measure spontaneous model regressions.

The harness submits three concurrent fixture jobs (the recorded initial local run used three closely spaced sequential HTTP submissions) to one worker with domain/browser concurrency one. Latency includes queue wait; p95 is the nearest-rank statistic with only three observations. Hardware and sample sizes are reported. No inference throughput, high-load capacity or scalability claim follows from this test.

A and B are audit-only comparisons and have no repair success metric. C is the full workflow. Fixture auditing is deterministic, not a substitute live single-prompt/RAG comparison. The live comparison command is prepared but disabled by default:

```sh
python evals/compare_live.py --help
```

Do not enable its paid execution until the account is funded and the remaining validation ledger is checked. Existing reservations are retained: USD 2 reserved, USD 3.6345 unallocated under the previously configured EUR 5 ceiling/FX. Reservations are not measured charges. Provider usage and actual cost for the failed request are unknown.

## Human rubric

Use `evals/human-review-worksheet.csv`. An independent reviewer records business-fact accuracy (exact approved details), clarity, visual hierarchy, mobile readability, keyboard usability and overall appropriateness on 1–5 scales with evidence notes. Any invented credential/testimonial or changed contact detail is a factual failure regardless of visual ratings. Record reviewer/date and accept/reject separately from executable results. No human scores have been filled in. LLM judges are supplementary only after calibration against these independent labels; none has been used here.

## Operations and limitations

PostgreSQL LangGraph checkpoints, durable step journals, Redis recovery and stable artifact IDs support restart and duplicate delivery. Active execution time is budgeted cumulatively; review idle time is excluded. Node timing events are tenant-owned and inspectable at the events endpoint. Queue retries remain bounded; provider HTTP rejection does not trigger automatic paid retries. Single-host Compose is the supported deployment; horizontal operation would require distributed limits and measured load testing.

Automated tests do not assess real model reasoning, semantic retrieval, real client designs, conversion impact or independent human quality. Optional reranking remains disabled. Secrets never appear in reports. The initial 429 subtype was unavailable; the user separately confirmed zero account balance. Existing live jobs retain their failure and mode.

The recovery implementation follows the official [LangGraph checkpointer state-update contract](https://docs.langchain.com/oss/python/langgraph/checkpointers#update-state): `as_node` determines which node executes next. Budget refresh explicitly identifies the completed predecessor to retain the pending operation.

Capture monitors the worker connection using the official [Starlette request disconnect API](https://starlette.dev/requests/). After disconnect, remaining viewport/Lighthouse runs stop; an already running Lighthouse subprocess retains its 45-second timeout and profile cleanup. This releases the single browser slot rather than finishing all measurements for a terminated worker. Partial/cancelled evidence cannot pass verification.
