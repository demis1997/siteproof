# Observed validation — 6 October 2026

Scope of this milestone: Phases 1–2. Existing Designer/Verifier functionality was preserved; no new Phase 3 feature was added. The code tested locally is commit `983658c`; reports retain actual fixture job IDs. Earlier host-browser and CI failures are historical failed observations, not successful tests.

## Passed

- Real isolated Docker Compose stack: PostgreSQL with pgvector 0.8.7, Redis, pinned-source MinIO, API, workflow worker, isolated capture browser/proxy, fixture HTTP service and Next.js frontend. Migrations ran against PostgreSQL. API readiness and dashboard connectivity succeeded without deleting unrelated volumes.
- `evals/stack_run.py` completed six ordinary fixture audits: clean, mobile overflow, broken contact, missing label, conflicting facts and prompt injection. Each had actual desktop/mobile PNGs, DOM, axe and Lighthouse results. Artifacts were stored in MinIO and authenticated retrieval returned PNG bytes; unauthenticated access was denied.
- The real delayed timeout job reported partial capture/unavailable evidence. A separate dashboard browser test signed in, submitted another overflow audit, observed background progress, loaded both images and navigated a finding to evidence. Fixture mode remained visible.
- Actual worker SIGKILL during capture/restart recovered the job via Redis and PostgreSQL LangGraph state. Browser-busy HTTP 429 caused bounded retry. Idempotent submission returned one job; duplicate completed queue delivery left one model run. This is a single recovery scenario, not a statistical recovery rate.
- Fact correction survived API/worker restart. Actual finding/fact approval persisted. Cross-tenant job access returned 404. Evidence IDs were unique and all finding/fact references existed.
- Actual PostgreSQL FTS/pgvector/RRF query mechanics, tenant/model filtering, persisted successful-substep reuse and uncertain-paid-step review guard passed. Synthetic vectors were transactionally rolled back and never presented as provider embeddings.
- Deletion of the harness-owned inactive clean job removed database rows, checkpoints and actual MinIO objects. Unrelated test/user jobs remain intact.
- 78 Python tests passed; Ruff passed; web lint, TypeScript, production build and four renderer tests passed. GitHub run [37468331014](https://github.com/demis1997/siteproof/actions/runs/37468331014) passed all four jobs, including real-stack integration, on commit `bd661ca`. The subsequent thread-pool fix passed the complete local harness; its newer CI run is tracked separately.
- PostgreSQL keyword retrieval measured recall@1=1.0, recall@3=1.0 and MRR=1.0 over four engineer-reviewed authored queries and four `guidance-v1` documents. The tiny authored set has no independent reviewer or held-out split.

Reports: `evals/reports/stack/report.json`, `report.md`, `retrieval.json`, `ui-result.json`, `dashboard.png`, `overview.png`. Static nine-fixture contract evaluation and local lexical smoke reports remain separate; they are not model-quality or end-to-end performance benchmarks.

## Repairs

Pinned official MinIO source build after prebuilt registry denial; loopback API/web ingress; narrow fixture-only HTTP proxy routing; Playwright route callback binding; viewport-unique axe IDs; sequential browser/Lighthouse lifecycle and owned Chrome cleanup; bounded Node pools/Chromium fan-out after an observed PID-limit abort; host-aware CSRF checks; secure idempotency generation on internal HTTP; durable Auditor journal/usage restoration; incremental embedding charging and versioned cache identity; stable guidance snapshots, validation and display; conflicting-contact provenance; real-stack/retrieval/recovery/deletion harnesses.

## Blocked and remaining limits

- Live vision/text/embedding audit is UNVERIFIED: `SITEPROOF_MODEL_KEY` and all three model prices are absent. Configure exact variables in `docs/PHASE12.md`; do not send secrets in chat. Fixture results never substitute for live AI. Returned provider usage/cost and real paid-call crash windows have not been observed.
- Vector-only/hybrid semantic ranking comparison is BLOCKED without real embeddings. Their report metrics are null; SQL mechanics success does not establish relevance or hybrid superiority.
- Optional reranking is unverified; Langfuse is absent. Local model records and structured logs are implemented.
- No production penetration/load test, independent human design ratings, client study, conversion experiment or Phase 4 A/B/C benchmark was performed. Earlier development dependency audit had unresolved lint-toolchain findings; this milestone does not claim a clean full dependency audit.
- Inline private-preview Lighthouse remains unavailable. Acceptance/build/redesign behavior was not expanded or newly certified by this Phase 1–2 milestone. Retention cleanup remains operator-triggered; backup/provider retention needs its own policy.

The Phase 1–2 local fixture definition of done is satisfied with the explicitly permitted missing-credentials live-verification exception. Live AI and semantic retrieval quality remain blocked. This does not establish whole-product completion or production readiness.

## Reproduce

```sh
test -f .env || cp .env.example .env
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.integration.yaml --profile integration -p siteproof-integration up --build -d
python evals/stack_run.py
ruff check services evals
pytest -q
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm run test:renderer --prefix apps/web
python evals/run.py
python evals/retrieval_run.py
```

Use the locked Python/Node dependencies and runtimes documented in README. The named integration project isolates storage; its fixed test tenant keys are only for the controlled development workflow.

Final code CI: [run 37469005781](https://github.com/demis1997/siteproof/actions/runs/37469005781) passed backend, frontend, isolated browser and real-stack jobs on `983658c`. Subsequent documentation/report commits retain the same application code; their own CI status should be inspected separately.
