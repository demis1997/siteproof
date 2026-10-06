# Observed local retrieval smoke evaluation

Generated 2026-10-06T11:38:46.116743+00:00. Queries: 4.

Real small guidance corpus, local token-overlap title/body ranks, actual application RRF; independent of auditor.

## Measurements
- local_lexical_rrf_recall_at_1: 1.0
- local_lexical_rrf_recall_at_3: 1.0
- local_lexical_rrf_mrr: 1.0
- duplicate_rank_entry_invariance: True
- postgres_fts_recall_at_k: unavailable
- pgvector_recall_at_k: unavailable
- reranker_quality: unavailable

## Limitations
- Four authored relevance queries over four guidance documents; no independent human labels or held-out retrieval benchmark.
- Both rankings are lexical token overlap; title/body RRF is not semantic hybrid search.
- PostgreSQL tenant filters, full-text ranking, vector embeddings and reranking not executed by this evaluator.
- Duplicate rank entries tested against actual application fusion function, not database content deduplication.
