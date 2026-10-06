# Observed real-stack fixture integration
Completed fixture samples: 6. Local code commit: `983658c`.
Additional actual timeout and dashboard-submitted overflow jobs passed. PostgreSQL checkpoint/journal/retrieval mechanics and physical PostgreSQL/MinIO deletion passed. Finding/fact approval also persisted.

The worker was killed during capture and restarted; correction survived API/worker restart, and duplicate completed delivery retained one model run. UI checks loaded both PNGs and navigated a finding to evidence.
- clean: PASS; evidence=20, findings=0, facts=6
- overflow: PASS; evidence=20, findings=1, facts=6
- broken-contact: PASS; evidence=20, findings=2, facts=6
- missing-labels: PASS; evidence=22, findings=6, facts=6
- conflicting-facts: PASS; evidence=20, findings=0, facts=8
- prompt-injection: PASS; evidence=20, findings=0, facts=6

## PostgreSQL retrieval
Corpus documents: 4; queries: 4.
- keyword: {'recall_at_1': 1.0, 'recall_at_3': 1.0, 'reciprocal_rank': 1.0}
- vector: BLOCKED: real embeddings not configured
- hybrid: BLOCKED: real embeddings not configured

## Limits
- Fixture audit results are not live AI results or client performance.
- Synthetic vectors test SQL mechanics only; no semantic vector/hybrid relevance measurement without credentials.
- No claim of production readiness or Phase 3 completion.

Final code CI: [run 37469005781](https://github.com/demis1997/siteproof/actions/runs/37469005781) passed backend, frontend, isolated browser and real-stack jobs on `983658c`. Subsequent documentation/report commits retain the same application code; their own CI status should be inspected separately.
