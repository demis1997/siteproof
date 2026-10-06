# Observed contract evaluation

Generated 2026-10-06T20:27:43.052168+00:00. Samples: 9.

Static HTML contact/label extraction and actual deterministic auditor/verification contracts; not browser or model quality.

## Observed metrics
- source_finding_precision: 1.0
- source_finding_recall: 1.0
- evidence_support_rate: 1.0
- source_finding_count: 2
- regression_rejection: True
- missing_checks_rejection: True
- missing_rendered_fact_evidence_rejection: True
- complete_checks_contract_acceptance: True
- hypothesis_remains_unverified: True
- contact_fact_mutation_rejection: True
- p50_contract_latency_seconds: 0.00020462501561269164
- p95_contract_latency_seconds: 0.0009369169711135328
- retrieval_recall_at_k: unavailable
- targeted_browser_repair_success: unavailable
- new_browser_regression_rate: unavailable
- workflow_recovery_rate: unavailable
- cost_per_accepted_preview: unavailable

## Baseline comparison
- A_single_prompt: not_run — Requires configured live model and controlled prompt experiment
- B_rag_auditor: not_run — Requires database retrieval and configured live model
- C_full_workflow: not_run — This harness evaluates contracts only; separate E2E/browser test required

## Limitations
- Labels are source-inspected, not independently browser/human verified.
- Nine related variants from one synthetic business; no client generalization.
- Overflow, geometry, navigation semantics, timeout and partial capture need browser tests.
- A/B/C quality comparison, embeddings, live providers and actual accepted-preview cost were not measured.
