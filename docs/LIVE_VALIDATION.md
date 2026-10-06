# Live AI and semantic retrieval validation

The verified fixture milestone is preserved. This milestone cannot certify live provider behavior without actual credentials. Keys are absent in the observed environment and private `.env`; no paid audit or embedding request has been run. There is no silent fixture fallback.

## Configuration (private `.env` only)

- `SITEPROOF_MODE=live`
- `SITEPROOF_MODEL_URL`: Chat Completions base URL; `/chat/completions` is appended.
- `SITEPROOF_MODEL_ID`: configured vision + structured-output model (existing default `gpt-4.1-mini`). Returned alias/snapshot must match; records retain the actual returned model.
- `SITEPROOF_MODEL_KEY`: chat credential.
- `SITEPROOF_EMBEDDING_URL`: separate embedding base URL; blank uses `MODEL_URL`.
- `SITEPROOF_EMBEDDING_MODEL`: existing default `text-embedding-3-small`, 1536 dimensions.
- `SITEPROOF_EMBEDDING_VERSION`: explicit operator-controlled cache revision.
- `SITEPROOF_EMBEDDING_KEY`: embedding credential. Alternatively set `SITEPROOF_EMBEDDING_USE_MODEL_CREDENTIALS=true` only after confirming the same account/key supports both endpoints. Credential sharing is off by default; endpoint compatibility does not establish account permission.
- `SITEPROOF_INPUT_COST_PER_MILLION`, `SITEPROOF_OUTPUT_COST_PER_MILLION`, `SITEPROOF_EMBEDDING_COST_PER_MILLION`: actual selected-provider USD prices. Missing values remain unknown. `SITEPROOF_REQUIRE_KNOWN_PRICES=true` explicitly rejects unpriced runs; otherwise token/call/time limits remain active and monetary enforcement is unavailable.
- `SITEPROOF_USD_PER_EUR`: operator-supplied current exchange rate, required to relate configured USD estimates to the EUR5 ceiling when all prices are known. Never infer provider invoice cost or a verified euro ceiling from unknown prices.
- `SITEPROOF_LIVE_VALIDATION_SESSION=live-validation-v1`: shared PostgreSQL ledger. API permits at most three NEW live audits, and the semantic evaluator at most one paid run in this session. Idempotent duplicate submissions do not allocate again. Each priced operation reserves USD1 against EUR5 using the supplied rate; uncertain/failed allocations are never refunded automatically. No reset/repeated experiment is authorized. This is a validation allocation cap, not a global provider-account spending guarantee.
- `SITEPROOF_VALIDATION_TENANT_KEY`: private CLI API tenant credential. This and model keys never enter frontend configuration.

A provider can support Chat Completions while using different embedding authorization. Verify each with the operator-configured credentials. Model/version/1536 dimensions and endpoint fingerprint must match indexing and queries. Optional reranking is disabled in the benchmark.

Official contracts: [vision](https://developers.openai.com/api/docs/guides/images-vision), [selected model](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create). These docs establish request shapes and model modalities, not this account's access. Conservative vision token allowances remain configurable and require calibration against actual usage; monetary figures are configured estimates, not invoices.

## Start real services

Install locked dependencies as in README. Keep existing `.env` and volumes. If the fixture integration project currently occupies localhost ports, stop it with `down` (never `down -v`) before starting the live project:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.integration.yaml --profile integration -p siteproof-integration down
docker compose --env-file .env -f infra/compose.yaml up --build -d
docker compose --env-file .env -f infra/compose.yaml exec -T worker python -m siteproof.migrate
```

Do not use the fixture integration override for a live run: it explicitly forces fixture mode. Keep `SITEPROOF_TEST_FIXTURE_HTTP=false`; live URL restrictions are unchanged. Host an operator-controlled English service-business fixture on a public HTTP(S) address. Do not bypass private-network restrictions for a live model test.

## One bounded audit

The runner submits only one job; repeat only if necessary, within the same persisted session and at most three total. Server-side allocation applies to dashboard submissions too. It does not modify facts, accept a preview or interrupt a paid call.

```sh
mkdir -p evals/reports/live
docker compose --env-file .env -f infra/compose.yaml exec -T -e SITEPROOF_CODE_COMMIT="$(git rev-parse HEAD)" worker python evals/live_audit_run.py --tenant local --url https://YOUR-CONTROLLED-PUBLIC-FIXTURE.example > evals/reports/live/audit.json
```

For a missing-key preparation report, omit `--url`; no job/provider is called. A successful audit report compares fetched PNG bytes/hash/size with the actual transmitted data-URL metadata, records returned models/usage/guidance, and classifies findings from executable evidence. Matching request bytes do not independently prove remote visual comprehension. Inspect the authenticated dashboard: explicit Live mode banner, real model runs, source citations, both images, fact approval/correction, and persistence after restart. The runner leaves UI and human wording review explicitly unverified until these inspections actually occur. Use `--job-id` to inspect an existing job without another paid submission.

## Retrieval benchmark

`knowledge/retrieval-benchmark-v1.json`: 18 documents, four short attributed original paraphrases of fetched W3C pages plus 14 explicitly local policies/distractors. No official-source text is fabricated or represented as a quotation. `evals/retrieval-dataset-v1.json`: 32 queries, 16 development and 16 held-out; four no-answer queries in total, paraphrases and graded overlapping relevance. Labels were authored by the coding agent and REQUIRE independent human review. Topic/paraphrase families span both sets, so this is not held-out website generalization.

The evaluator seeds only a dedicated `retrieval_benchmark_` tenant; application guidance/facts remain unchanged. Versioned content hashes reject stale corpus reuse. Corpus and query embeddings are cached by tenant/content/model/version/dimensions/endpoint. The initial comparison uses frozen raw keyword/vector/RRF rankings; no tuning was performed. Any later threshold/weight tuning must use development labels only before a fresh held-out evaluation.

Keyword preparation (no paid calls):

```sh
docker compose --env-file .env -f infra/compose.yaml exec -T -e SITEPROOF_CODE_COMMIT="$(git rev-parse HEAD)" worker python evals/semantic_retrieval_run.py > evals/reports/live/retrieval.json
```

Actual semantic comparison, once credentials are configured, ONE allocation in the SAME session:

```sh
docker compose --env-file .env -f infra/compose.yaml exec -T -e SITEPROOF_CODE_COMMIT="$(git rev-parse HEAD)" worker python evals/semantic_retrieval_run.py --live-embeddings > evals/reports/live/retrieval.json
```

Report: recall@3/@5, MRR, nDCG@5, actual SQL p50/p95 query latency, embedding calls/tokens/known-or-unknown cost, separate raw no-answer false-answer rate, dataset/corpus hashes and versions. Embedding latency/usage is separate from SQL query latency. Nearest-neighbor/RRF retrieval has no calibrated abstention guarantee: irrelevant results are reported, not silently declared correct. Missing keys keep semantic metrics null; synthetic vectors are never semantic benchmark results. Interrupted paid runs must be investigated rather than automatically replayed; the ledger prevents another automatic benchmark allocation.

## Simulated tests versus observations

`services/tests/test_live_validation.py` uses deterministic HTTP transports for missing credentials, separate keys, PNG request bytes, malformed output, incorrect models/dimensions, timeouts, HTTP401/429/500, budgets and unknown cost. Journal tests simulate success replay, transport interruption and a response lost before durable save. These are NOT live-provider measurements and do not establish exactly-once model execution.

Run `pytest -q`, `ruff check services evals`, web lint/types/build/renderer tests and the existing real-stack fixture harness. Actual PostgreSQL allocation tests use simulated prices/FX without paid calls. Live hypotheses stay uncertain until independently reviewed; executable evidence can support objective defect categories but not every phrasing or inferred business effect. Existing Phase 3/4 limitations remain unchanged.
