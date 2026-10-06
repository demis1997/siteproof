# SiteProof implementation plan

1. Deterministic slice: tenant-authorized API, Redis queue, safe browser capture, DOM/axe/Lighthouse evidence, dashboard, Compose.
2. Grounded analysis: validated findings, provenance-bearing facts, curated guidance, hybrid retrieval, explicit fixture/live providers.
3. Controlled redesign: typed React sections, private preview, equivalent before/after checks, bounded repair and review.
4. Reliability: budgets, checkpoint recovery, security tests, reproducible fixture evaluation, CI and operational documentation.

Assumptions: single-host deployment; one homepage; English service businesses; fixture mode explicitly labelled; API bearer tokens provision tenants; no publishing. Completion requires executable verification; unavailable checks remain unverified. Browser egress uses a validating forward proxy in an internal Docker network. Three bounded development agents own backend, frontend, and evaluation/docs; integration remains with the primary engineer.
