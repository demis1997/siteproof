# Observed real-stack fixture integration
Completed fixture samples: 6.
- clean: PASS; evidence=20, findings=0, facts=4
- overflow: PASS; evidence=20, findings=1, facts=4
- broken-contact: PASS; evidence=20, findings=2, facts=4
- missing-labels: PASS; evidence=22, findings=6, facts=4
- conflicting-facts: PASS; evidence=20, findings=0, facts=6
- prompt-injection: PASS; evidence=20, findings=0, facts=4

## PostgreSQL retrieval
Corpus documents: 4; queries: 4.
- keyword: {'recall_at_1': 1.0, 'recall_at_3': 1.0, 'reciprocal_rank': 1.0}
- vector: BLOCKED: real embeddings not configured
- hybrid: BLOCKED: real embeddings not configured

## Limits
- Fixture audit results are not live AI results or client performance.
- Synthetic vectors test SQL mechanics only; no semantic vector/hybrid relevance measurement without credentials.
- No claim of production readiness or Phase 3 completion.
