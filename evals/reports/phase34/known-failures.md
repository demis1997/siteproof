# Development failures retained in the audit trail

- First live request: embedding HTTP 429, subtype unavailable; user confirmed zero balance. No retry, no successful embeddings or text/vision analysis. Actual inference cost unknown.
- Initial fixture run failed because TraceEvent was not in the SQL record-kind constraint. Added migration 002 and applied it; later full pipeline passed.
- First recovery probe exposed LangGraph budget-update inference advancing past the pending verifier. Fixed updates to explicitly name the predecessor, added a regression test, and recovered the interrupted fixture.
- A subsequent interruption resumed verification but mobile Lighthouse was unavailable during concurrent image building. Required checks failed and the job stayed needs_review; no acceptance was granted. The clean interruption rerun is reported separately.
- UI harness started once before web startup and then used an unauthenticated context for its preview probe. Corrected startup ordering and authenticated browser context; observed UI checks passed.

These are development observations, not omitted benchmark samples or live model quality judgments. Functional reports identify their successful samples and synthetic scope. Human quality remains unreviewed.
