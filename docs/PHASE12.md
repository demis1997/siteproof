# Phase 1–2 verification checklist

Scope: finish capture, deterministic audit and grounded AI/retrieval. Existing Designer/Verifier functionality is preserved. This document records the current verification boundary; CI artifacts record each actual run.

## Verified before this milestone

- Local unit/contract tests, frontend lint/types/build, renderer authorization and escaping.
- GitHub run 37459673262 passed backend, frontend and isolated browser slice. The browser slice is not a full-stack job submission test.

## Verified locally against real services — 6 October 2026

- Real PostgreSQL/pgvector, Redis, MinIO, API, single-host worker and frontend Compose integration job.
- HTTP fixture capture through a fixed test-only proxy mapping; real axe/Lighthouse and screenshots.
- LangGraph PostgreSQL checkpoints plus durable Auditor substep journal. Persisted successful results are reused; uncertain paid calls stop for review. Explicit provider 429 rejections are retryable; unknown transport outcomes are not automatically replayed.
- Persisted fact corrections, tenant-scoped artifacts and deletion.
- Actual PostgreSQL FTS/vector/RRF mechanics assertions, checkpoint persistence, cached-success replay guard, uncertain paid-call review guard, and tenant/model filtering passed. Synthetic vectors verify mechanics only.
- Combined `evals/stack_run.py` passed six standard fixture audits, a real timeout/partial-capture job, and an additional UI-submitted overflow job. Authenticated screenshots loaded in the browser and evidence navigation passed. Physical PostgreSQL/checkpoint/MinIO deletion passed for the harness-owned clean job.
- Actual finding/fact approval passed; corrected email persisted across API/worker restart.
- Keyword retrieval: recall@1=1.0, recall@3=1.0, MRR=1.0 on four authored queries/four documents (`guidance-v1`). Vector/hybrid relevance remains blocked.
- GitHub [run 37468331014](https://github.com/demis1997/siteproof/actions/runs/37468331014) passed all four jobs, including real-stack integration (`bd661ca`).
- 78 Python tests, Ruff, web lint/types/production build and four renderer tests passed. Current code verification commit: `983658c`. Earlier failed runs remain failures; this is one successful local combined run, not a reliability estimate.

## Blocked or unavailable

- Live model credentials and three configured prices are missing. No real vision/text/embedding audit or semantic retrieval comparison has been run.
- Optional reranking remains unverified; Langfuse remains optional and absent.

## Exact integration commands

Copy `.env.example` to `.env` only if `.env` does not already exist. The integration override explicitly enables the fixed HTTP fixture host and provisions the two test tenants. The named `siteproof-integration` project uses separate volumes; do not overwrite an existing personal `.env`.

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.integration.yaml --profile integration -p siteproof-integration up --build -d
python evals/stack_run.py
```

The harness uses only its marked integration tenant/jobs. It kills/restarts the worker, restarts API, corrects a fact, tests duplicate delivery, inspects browser images and evidence navigation, and deletes one of its own jobs. JSON reports and a UI screenshot are saved under `evals/reports/stack`. Failed assertions mean the milestone has not passed.

Run migrations idempotently on existing databases without dropping volumes:

```sh
docker compose --env-file .env -f infra/compose.yaml run --rm init
```

MinIO is built from the pinned upstream source commit because the previously configured public image repositories returned access denied. Source/license: https://github.com/minio/minio/tree/RELEASE.2025-09-06T17-38-46Z (AGPLv3). This build requires dependency downloads; no storage migration or volume deletion is performed.

## Live audit

Configure these in the private `.env` file (never paste keys into chat):

- `SITEPROOF_MODE=live`
- `SITEPROOF_MODEL_KEY`
- `SITEPROOF_MODEL_URL`, `SITEPROOF_MODEL_ID`
- `SITEPROOF_EMBEDDING_MODEL` (1536-dimensional support required)
- `SITEPROOF_EMBEDDING_VERSION` (change when embedding behavior/version changes)
- `SITEPROOF_INPUT_COST_PER_MILLION`
- `SITEPROOF_OUTPUT_COST_PER_MILLION`
- `SITEPROOF_EMBEDDING_COST_PER_MILLION`

Leave `SITEPROOF_TEST_FIXTURE_HTTP=false` in live mode. Recreate API/worker/browser with Compose so configuration takes effect, then submit a public website via the authenticated dashboard. Inspect `/runs` for actual model usage, image hashes/IDs supplied to the vision request, and guidance source IDs. These request records do not independently establish that a remote provider processed the images correctly.

```sh
docker compose --env-file .env -f infra/compose.yaml up -d --force-recreate api worker browser
docker compose --env-file .env -f infra/compose.yaml exec -T worker python evals/postgres_retrieval_run.py --tenant local > evals/reports/live-retrieval.json
```

The evaluator compares keyword/vector/hybrid recall@1, recall@3 and MRR on four manually checked authored queries and four corpus documents. With missing credentials/prices only PostgreSQL keyword measurements run; vector/hybrid metrics remain null. Synthetic vectors in `db_checks.py` verify SQL mechanics and tenant/model filtering, not embedding relevance. No claim that hybrid beats another arm is made.

Final code CI: [run 37469005781](https://github.com/demis1997/siteproof/actions/runs/37469005781) passed backend, frontend, isolated browser and real-stack jobs on `983658c`. Subsequent documentation/report commits retain the same application code; their own CI status should be inspected separately.
