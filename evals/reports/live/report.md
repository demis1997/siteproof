# Observed live-validation preparation
Code commit: `66596630c0ee19cf0f1d413947e3251bfc724335`. Corpus: `retrieval-corpus-v1`. Dataset: `retrieval-dataset-v1`.
Live audit: **BLOCKED**. Actual live audits submitted: 0. Cost USD: unknown.
Set live mode, SITEPROOF_MODEL_KEY and separate embedding key or explicit sharing. No provider call was attempted.
Corpus documents: 18; queries: 32 (16 dev/16 held-out, including four no-answer).

## Actual PostgreSQL retrieval

### dev
- keyword: recall@3=0.7500, recall@5=0.7500, MRR=0.9286, nDCG@5=0.8804; SQL p50=4.565 ms, p95=4.981 ms; answer-bearing queries=14.
- vector: BLOCKED; real embeddings not generated.
- hybrid: BLOCKED; real embeddings not generated.
- Keyword no-answer: 1/2 empty; false-answer rate=0.50. These are raw rankings, not calibrated abstention.

### held_out
- keyword: recall@3=0.8571, recall@5=0.8929, MRR=0.8929, nDCG@5=0.8176; SQL p50=4.630 ms, p95=5.205 ms; answer-bearing queries=14.
- vector: BLOCKED; real embeddings not generated.
- hybrid: BLOCKED; real embeddings not generated.
- Keyword no-answer: 1/2 empty; false-answer rate=0.50. These are raw rankings, not calibrated abstention.

## Verification boundary
- Live vision/text/embedding behavior is unverified. No fixture result substituted for a live call.
- New HTTP/journal failure scenarios are simulated, not provider observations; actual check results are in validation-checks.json.
- Real PostgreSQL allocation gates passed using simulated prices/FX, with no paid calls.
- Existing real-stack fixture regression passed six ordinary fixtures, real timeout, dashboard PNG/evidence navigation, recovery, correction persistence and deletion.
- Labels were authored by the coding agent; independent human quality/relevance review is required.
- No tuning performed. Semantic arms remain null. No hybrid superiority or production readiness claim.
- No paid interruption performed; no exactly-once remote execution claim.
- Existing Phase 3 work preserved; redesign feature validation and Phase 4 comparison remain outside this milestone.
