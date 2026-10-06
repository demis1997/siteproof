# Observed validation — 6 October 2026

Implemented in a new, isolated `siteproof/` Git repository. No pre-existing project files were replaced. Development used three bounded implementation agents; the application workflow contains exactly three named LangGraph nodes: Auditor, Designer, Verifier.

## Passed locally

- Python 3.12: **66 tests passed**. Coverage includes unsafe URL/IP cases, empty credentials, DNS answer validation, tenant isolation, atomic idempotency contract, outbox dispatch failure behavior, evidence references, model credential/pricing gates, estimated cost accounting, protected facts/contact destinations, missing viewport checks, regression detection, two-repair bound, cancellation guards, and in-memory checkpoint resume.
- Ruff lint passed over `services` and `evals`.
- Web lint, TypeScript, and production build passed with Next.js 16.3.8, React 19.3.0, TypeScript 6.0.3. TypeScript 7 was incompatible with the lint toolchain, so the compatible stable version is pinned.
- **Four renderer tests passed**: internal authorization, invalid specification rejection, escaped semantic React HTML/fact preservation/CSP, and unsafe contact destination exclusion.
- Actual HTTP smoke: dashboard 200; unauthenticated renderer 403; authenticated controlled renderer 200; unauthenticated private preview API 401. Rendered HTML retained provided services/hours/prices, escaped an injected script string, emitted no script tag, and included noindex/CSP headers.
- Actual API smoke: health 200, unauthenticated jobs 401, readiness 503 while database/queue dependencies were absent. A readiness failure was not presented as a working database integration.
- Docker Compose configuration validated with the development environment file. Container startup was **not** verified.
- Actual static contract evaluation ran over nine related synthetic fixtures, detecting two labelled source-check defects. Results are in `evals/reports/report.json` and `.md`.
- Actual independent retrieval smoke ran over four authored queries and four guidance documents using local lexical ranking and the application RRF function. SQL/vector/reranking quality remains unmeasured.
- Browser-tool dependency audit after updating Lighthouse/axe reported zero vulnerabilities. Production web dependency audit reported zero vulnerabilities. The full web development dependency audit reported five high findings through the lint toolchain's `braces` dependency; no compatible upstream fix was identified. These are unresolved development-tool findings, not a clean full dependency audit.

## Blocked or unverified

- Docker daemon was unavailable. Launching the installed Docker app failed; its application launcher reported a missing executable and direct launch aborted. PostgreSQL migrations, Redis delivery/restart behavior, MinIO artifact storage/deletion, and full Compose startup remain unverified against running services.
- Chrome and Chromium aborted in the host sandbox. Chromium reported `MachPortRendezvousServer: Permission denied (1100)`. The attempted browser evaluation saved failure reports with **zero completed samples and null metrics**. No before/after screenshot, axe execution, Lighthouse execution, or browser repair success was claimed from that attempt.
- Live vision/text/embedding requests require credentials and configured model prices. Provider HTTP contracts were exercised using explicit test doubles; no real model response or invoice was measured.
- Optional Hugging Face TEI reranking is implemented, but no configured reranker was exercised. Langfuse integration is not implemented; model runs and structured logs provide local observability.
- GitHub Actions is authored but has not been run remotely. The Ubuntu browser job is intended to execute the actual renderer/capture slice when its environment permits browser launch.
- No production SSRF penetration test, load test, independent human labels, human design ratings, live-user study, or conversion experiment was performed.

## Remaining verification commands

Run the README Compose commands on a host with a functioning Docker Engine. Verify a fixture audit → approvals → redesign → measured checks → manual acceptance. Exercise failed verification, cancellation, worker restart, two tenants, expired/deleted artifacts, and a credentialed live job. Run the browser harness and review its screenshots/labels before using browser metrics as portfolio results.

The definition of done requiring a verified full-stack fixture workflow is **not yet satisfied in this environment**. The implementation and runnable checks are delivered; unavailable integration outcomes remain explicitly unverified.
