# Prepared live benchmarks — do not run while requests are stopped

Current state: zero OpenAI balance, paid requests stopped. Existing live jobs have not been converted to fixtures. No command in this document has been executed as part of the current fixture validation.

## Safe preparation now

With the separate fixture stack running:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.integration.yaml --profile integration -p siteproof-integration exec -T worker python evals/compare_live.py
```

This prints experiment configuration only. It does not request a model or embedding.

## Later, after funding and renewed authorisation

First inspect the unchanged live ledger and agree which remaining allocations to use. Its saved SQL snapshot records one audit and one retrieval reservation, USD 2 total. Two audit slots remain; the single retrieval slot is already used. A failed request does not automatically refund a reservation. Standalone paid semantic benchmarking will therefore stop at its allocation guard unless an additional retrieval allocation is explicitly authorised. Do not change session IDs or reset counts to bypass the ceiling.

The existing live capture `4b355933-0f79-48f1-a614-28ae9ab65cd7` contains real controlled-fixture screenshots and DOM but no successful AI analysis. Read-only inspection does not submit a new job:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.live-validation.yaml --profile integration -p siteproof exec -T worker python evals/live_audit_run.py --tenant local --job-id 4b355933-0f79-48f1-a614-28ae9ab65cd7
```

The normal live stack must be deliberately started later; do not use the integration override, which forces fixture providers. Keep the documented exact-host test exception and production URL protections. Run only one stack on the shared local ports.

For the prepared A/B comparison, the following is an explicit **paid opt-in**, consuming up to the two remaining audit allocations. It reuses the same durable capture and model configuration, with guidance absent for A and hybrid guidance present for B. An HTTP rejection stops the experiment, not a fixture fallback:

```sh
mkdir -p evals/reports/live
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.live-validation.yaml --profile integration -p siteproof exec -T -e SITEPROOF_ALLOW_PAID_BASELINES=true worker python evals/compare_live.py --tenant local --job-id 4b355933-0f79-48f1-a614-28ae9ab65cd7 --execute > evals/reports/live/baselines.json
```

Token, call, time and monetary guards may stop the experiment. Prepared code is not a verified live integration. A/B are audit-only arms: repair success is not applicable. C requires a separately completed live redesign/verification workflow and enough remaining cumulative job budget; no live C quality result exists.

The reproducible semantic command remains prepared, not authorised for execution under the exhausted retrieval-slot limit:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.live-validation.yaml --profile integration -p siteproof exec -T worker python evals/semantic_retrieval_run.py --help
```

See `LIVE_VALIDATION.md` for its opt-in flags and cached evaluation behaviour. Never substitute synthetic vectors. Preserve the frozen dataset and report any no-answer failure. Provider usage plus configured rates produces a cost estimate, not an invoice; actual billed inference cost still requires billing evidence. Reranking remains disabled.
