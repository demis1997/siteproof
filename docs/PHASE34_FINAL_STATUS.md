# Phase 3–4 final fixture validation

Validated implementation: `61fed5e9fc86716a59c1e92dfb8a877a439d91fd`.
[Final GitHub Actions run](https://github.com/demis1997/siteproof/actions/runs/37531750994): all four jobs passed. The earlier run 37529904766 failed its navigation-timeout case; the capture fix was verified in the final run. Run 37531345204 was superseded and cancelled.

| Requirement | Result | Evidence |
|---|---|---|
| Controlled redesign rendering and preserved facts | PASS — fixture provider | `evals/reports/phase34/pipeline.json` |
| Real desktop/mobile before/after Lighthouse and axe | PASS | Two Lighthouse samples per viewport; pipeline evidence |
| Regressions reject acceptance, bounded repairs | PASS | `faults.json`: repaired at one attempt; persistent regression stopped at two; HTTP 409 on failed acceptance |
| Worker restart recovery | PASS | `recovery.json`: real SIGKILL during verifying, durable checkpoint and unique evidence |
| Authenticated preview and dashboard | PASS | `phase34-ui.json` and captured screenshots; human quality review pending |
| Deterministic evaluation and concurrent fixture load | PASS — limited sample | 3/3 concurrent submissions completed; p50 88.18s, p95 130.27s; one worker, browser/domain concurrency one |
| Tests and final CI | PASS | 138 Python tests, four renderer tests, lint/type/build checks; linked real-stack CI |
| No-answer retrieval calibration | FAIL / unresolved | `no-answer-development.md`: one of two development no-answer queries returned irrelevant guidance |
| Live model quality and A/B/C comparison | BLOCKED | Zero OpenAI balance; no further paid calls, no 429 retry |
| Semantic retrieval and actual inference costs | BLOCKED | No successful live embeddings in this validation; synthetic vectors only test mechanics; invoice cost unknown |
| Independent human labels/design quality | BLOCKED / pending | Agent-authored fixture labels and empty human review worksheet |

The original held-out label file is unchanged; related variants remain website-grouped. Earlier development exposure means it is not an independently unseen benchmark. Fixture results do not establish live AI quality, conversion effects, WCAG compliance, or production scalability.

The existing live ledger is preserved: USD 2 reserved, USD 3.6345 unallocated under its ceiling, with actual failed-request cost unknown. Reservations are not charges. Live jobs were not converted to fixtures. Root `.env` remains private and live; only the separate integration stack uses explicit fixture providers with empty provider credentials. No deployment occurred.

Reproduction commands are in `PHASE34.md`; future paid opt-in commands and allocation restrictions are in `LIVE_BENCHMARK_LATER.md`. The final report-only commit does not change the implementation validated by CI.
