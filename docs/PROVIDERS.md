# Model providers

Fixture mode is deterministic and must show “Fixture data” throughout the dashboard. It does not call a model API, measure model intelligence, or provide real-business analysis. Live mode must fail clearly without configured credentials; it must never silently fall back.

The provider boundary covers vision input, validated structured text, embeddings, and optional reranking. Configure model IDs and version prompts independently. Record actual tokens, latency, prompt version, model ID, and known provider pricing for every call. Missing usage or monetary price remains unknown rather than zero. Treat images and extracted website text as untrusted context.

A finding is acceptable only when every evidence ID exists in this job. A proposed design selects approved components and preserves critical source facts or an explicit user correction. A verifier may label design hypotheses unverified but cannot turn a failed executable check into a pass.

Before treating live integration as verified, run a real credentialed job, inspect provider responses, validate schema failures, budget failures and timeout handling, and compare provider invoices or usage telemetry. Optional observability must not receive sensitive page content by default.

## Implemented configuration

The live adapter uses strict JSON schema Chat Completions with low-detail screenshot inputs and a constrained designer schema. Executable objective findings are always generated deterministically; the model contributes grounded design hypotheses. Model self-approval is removed. The designer may choose layout/typography and service ordering, while protected source text and critical facts stay exact. Fixture mode uses no API key or invented embeddings.

Configure `SITEPROOF_MODEL_URL`, `SITEPROOF_MODEL_ID`, `SITEPROOF_MODEL_KEY`, `SITEPROOF_EMBEDDING_URL`, `SITEPROOF_EMBEDDING_KEY`, `SITEPROOF_EMBEDDING_MODEL` and version, and input/output/embedding USD-per-million prices. Sharing the chat key requires explicit `SITEPROOF_EMBEDDING_USE_MODEL_CREDENTIALS=true`; different providers/accounts may require separate credentials. All three prices are required only when `SITEPROOF_REQUIRE_KNOWN_PRICES=true` or an explicit monetary budget applies. Unpriced live jobs retain strict token/call/time limits and unknown cost. Recorded cost is an estimate from configured rates and actual returned usage, not billing reconciliation. Conservative preflight reserves output tokens, UTF-8 prompt size, and a configurable vision-token allowance; modality token assumptions must be recalibrated after a model change. Oversized evidence requests fail rather than silently truncating evidence IDs or removing the spending limit. Token, call, elapsed time and money usage persist between audit and redesign. Missing or failed remote usage accounting still requires live recovery validation.

Embeddings are tenant/content-hash/model cached at 1536 dimensions. The identity additionally includes `SITEPROOF_EMBEDDING_VERSION` and a model endpoint fingerprint, and returned model/index/dimensions are validated. Corpus/model changes invalidate vector entries. Tenant and collection filters precede lexical and semantic ranking. Business fact retrieval additionally requires homepage job scope. Only user-approved facts enter that collection. Guidance uses PostgreSQL FTS + pgvector, RRF, content deduplication, and optional `SITEPROOF_RERANK_URL` Hugging Face TEI `/rerank`. Reranking is opt-in and must be separately measured.

Official implementation references: [structured Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create), and [Hugging Face TEI reranking](https://huggingface.co/docs/text-embeddings-inference/en/quick_tour).

## Recovery boundary

Successful Auditor substeps and their returned usage are persisted in PostgreSQL. Embedding usage is charged incrementally before another paid call; resume restores durable usage into checkpoint state. A paid step left started without a persisted result is uncertain and requests review instead of replaying. Explicit provider HTTP 429 rejection permits a bounded retry; unknown transport outcomes do not. Real provider crash windows remain unverified without credentials. Guidance is snapshotted per job so later corpus updates cannot rewrite historical grounding.

See [the live validation milestone](LIVE_VALIDATION.md) for the shared three-audit/EUR5 allocation ledger, unpriced policy, expanded benchmark and actual observation boundaries. Model records hash decoded PNG bytes and retain byte counts, request IDs, actual response model and retrieval identity. These metadata demonstrate request transport and executable grounding, not remote visual comprehension or subjective quality.
