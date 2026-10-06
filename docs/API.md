# API reference

FastAPI publishes generated OpenAPI at `/docs`. The local API requires `X-Tenant-Key` on job and artifact routes; tenant identity is derived from this credential. The current local development tenant configuration is not a production multi-tenant identity provider.

- `POST /api/jobs`: `{ "url": "https://example.com", "goal": "optional" }`; require `Idempotency-Key`. Returns the existing job for the same key and URL, rejects key reuse for another URL.
- `GET /api/jobs`: recent jobs owned by the authenticated tenant.
- `GET /api/jobs/{id}`: status, stage, versions, budget and error data; dashboard polls this route.
- `GET /api/jobs/{id}/evidence`, `/findings`, `/facts`, `/verification`, `/runs`, `/captures`, `/guidance`: tenant-scoped records.
- `POST /api/jobs/{id}/approve`: `{ "finding_ids": [], "fact_ids": [] }`; rejects unknown identifiers and records approval.
- `POST /api/jobs/{id}/redesign`: requires audit completion and approval of findings and facts.
- `GET /api/jobs/{id}/preview`: typed page specification.
- `GET /api/jobs/{id}/preview-html`: authenticated, noindex HTML preview with a restrictive content security policy.
- `POST /api/jobs/{id}/review`: `{ "decision": "accept" }` or `reject`; failed or unavailable required verification prevents acceptance.
- `POST /api/jobs/{id}/cancel`: requests cancellation.
- `GET /api/artifacts/{job_id}/{artifact_id}`: authenticated screenshot delivery.
- `GET /health`: process health; `GET /ready`: database and queue readiness.

Errors use HTTP 401 for missing authentication, 404 for absent owned resources, 409 for invalid stage transitions or unsafe acceptance, and 422 for invalid input. Some legacy errors use string details while security and credential failures include `{code,message}`; consumers should display either form. An API response does not prove a workflow or external integration completed.

`POST /api/jobs/{id}/facts/{fact_id}/correct` accepts `{value,reason}` during review, records the original value and user correction, and invalidates prior verification. Corrections persist in PostgreSQL.

`DELETE /api/jobs/{id}` deletes an inactive tenant-owned job, artifacts, retrieval facts and checkpoints; active/busy jobs return 409. See the retention command and limitations in `SECURITY.md`.

`SITEPROOF_TENANT_KEYS_JSON` optionally supplies a JSON mapping of tenant identifiers to unique keys. Migration seeds each configured tenant and its own guidance corpus. The default local-development key is for a loopback-bound development instance only.

Guidance responses retain the source, version, reuse notes, and content seen by this job. A stored snapshot prevents later corpus edits from changing historical citations.
