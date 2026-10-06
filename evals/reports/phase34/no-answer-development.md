# Development-only no-answer investigation

Observed source: `retrieval-expanded.json`, real PostgreSQL full-text search with no model or embedding calls. Dataset and corpus files were not modified.

Of the two development no-answer queries, the revenue-forecast query returned no chunks. The checkout-tax-engine query returned `bench-budgets-v1`. The query contains “configure”; the unrelated budgets guidance contains “configured prices”. English stemming and the harness's OR expansion admit this generic lexical overlap despite the missing checkout/tax topic.

The development raw false-answer rate is 1/2 = 0.5. This means nonempty irrelevant retrieval on a labelled no-answer query, not a generated AI answer or an observed hallucination. The retained held-out aggregates are reported as observed; their individual examples were not used to tune a gate.

Status: **FAIL / unresolved abstention calibration**. Do not advertise keyword retrieval as reliably rejecting unsupported questions. A future answerability policy should be calibrated on a larger independently reviewed development set, distinguish topical evidence from generic-word matches, and allow no answer; reranking alone is not an abstention guarantee. Re-run the frozen test split only after the policy is fixed. Vector/hybrid quality and model answer quality remain **BLOCKED**. No synthetic vectors or fixture answers were substituted.
