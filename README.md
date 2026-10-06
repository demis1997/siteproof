# SiteProof

Evidence-backed homepage auditing and private redesign verification for English-language service businesses. The acceptance gate requires every mandatory executable check at desktop **1440 × 1000** and mobile **390 × 844**. Design hypotheses remain unverified; failed or missing checks prevent preview acceptance.

This repository implements a single-host vertical slice, with explicit deterministic fixture mode and an OpenAI-compatible live provider. It does not publish websites or claim conversion improvement. See [implementation plan](docs/IMPLEMENTATION_PLAN.md) and [architecture](docs/ARCHITECTURE.md).

## Local application

Requires Docker Engine with Compose, network access for image/dependency downloads, and approximately 4 GB available RAM. Run from this project folder:

```sh
test -f .env || cp .env.example .env
docker compose --env-file .env -f infra/compose.yaml up --build -d
docker compose --env-file .env -f infra/compose.yaml logs -f api worker browser web
```

Open http://localhost:3000 and sign in with the development tenant access key from `.env`. Fixture mode is visibly labelled. Submit `https://fixture.siteproof.test/overflow`, inspect source evidence, approve findings/facts, request a redesign, inspect verification, and accept only after required checks pass. Other fixture slugs: `clean`, `broken-contact`, `missing-labels`, `weak-navigation`, `conflicting-facts`, `prompt-injection`, `timeout`, `partial`.

```sh
curl http://localhost:8000/health
curl http://localhost:8000/ready
docker compose --env-file .env -f infra/compose.yaml down
```

Data persists in PostgreSQL, Redis AOF, and MinIO volumes. `down -v` permanently deletes local data. Private artifacts are streamed through tenant-authorized API requests. Preview HTML is authenticated, noindex, and served with a restrictive CSP. Browser workers have only an internal network and a DNS-pinning egress proxy; do not expose the capture service or remove its isolation.

## Development checks

Python 3.12 and Node.js 22.20 or later are supported development runtimes. Python dependencies and browser-tool dependencies are locked separately from the web app.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
ruff check services evals
pytest
python evals/run.py
npm ci --prefix infra
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

For browser evaluation, run the web server and the harness as documented in [evaluation methodology](docs/EVALUATION.md). GitHub Actions also defines a browser slice on Ubuntu. The original isolated browser job passed on GitHub; full-stack Phase 1–2 verification is tracked in [the milestone checklist](docs/PHASE12.md).

## Live provider configuration

Set `SITEPROOF_MODE=live`, `SITEPROOF_MODEL_KEY`, model/base URL, and separate embedding credentials (or explicit confirmed sharing) in `.env`. Configure the three current USD price settings for monetary enforcement; otherwise cost stays unknown with strict token/call limits. Live mode never substitutes fixture responses. Prices are user-configured estimates, not an invoice; unmeasured costs remain unknown. Structured outputs and screenshot inputs use the official [Chat Completions contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); embeddings use the official [embedding contract](https://developers.openai.com/api/reference/resources/embeddings/methods/create). Changing models requires testing modality support, schema support, embedding dimensions, and the conservative vision-token allowance. See [provider details](docs/PROVIDERS.md).

## Evidence and limits

DOM selectors, actual axe violations, viewport checks and Lighthouse results retain stable evidence IDs. Model findings referencing unknown IDs are rejected. All original content is treated as untrusted data. Contact facts retain source/capture provenance; candidate services and conflicting details need human approval. Only approved components render generated specifications, and the exact rendered HTML is captured and shown privately.

Private previews now receive two real Lighthouse measurements at each documented viewport through an ephemeral isolated document capability. Automated testing does not establish WCAG compliance. Link checks cover homepage fragment targets only; other pages are outside this job's scope. A three-job fixture-provider load test is recorded separately; no real-client conversion experiment or independent human design study has been performed.

See [API](docs/API.md), [security boundaries](docs/SECURITY.md), [deployment](docs/DEPLOYMENT.md), [baseline limitations](docs/BASELINES.md), and [demo/resume templates](docs/DEMO.md). Actual measured static-fixture results are in [the contract report](evals/reports/report.md). The historical host-browser failure report records an earlier sandbox limitation; subsequent real Docker capture and UI checks are tracked in [Phase 1–2 validation](docs/PHASE12.md).

## Verification in this development session

The final observed check results and remaining integration requirements are recorded in `docs/VALIDATION.md`. Real Docker services and browser checks are exercised separately from unit tests. Live model requests remain unverified without credentials and configured prices.

## Phase 1–2 integration milestone

See [the observed checklist and exact commands](docs/PHASE12.md). The integration profile uses an explicitly enabled HTTP fixture host to exercise real Lighthouse through the isolated proxy. Production/live URL restrictions remain enabled. MinIO now builds a pinned upstream source release because public prebuilt-image pulls returned access denied. Live AI and semantic retrieval results require private credentials and configured prices.

## Live AI and expanded retrieval validation

See [live configuration, budgets and exact commands](docs/LIVE_VALIDATION.md). The separate benchmark has 18 documents and 32 development/held-out queries; author-created labels still require independent human review. Real PostgreSQL keyword results are reported separately from blocked semantic/live checks. No paid calls run without credentials or an explicit operator command.

## Phase 3–4 fixture verification

See [implementation, exact commands, dataset and limitations](docs/PHASE34.md). The real-stack fixture pipeline covers redesign capture, before/after Lighthouse and axe, regression rejection, bounded repairs and private review controls. Live model quality, semantic retrieval and actual inference costs are BLOCKED while the OpenAI balance is zero. No paid requests will be retried.
