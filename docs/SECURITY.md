# Security and privacy

Public capture accepts only HTTP(S), rejects URL credentials, and blocks non-public DNS answers including loopback, private, link-local, reserved, and metadata addresses. Validate redirects and every subrequest; the browser must not resolve an already approved hostname again through an unrestricted network path. Production browser networking should pass through the restricted egress boundary. Application validation alone does not prove DNS-rebinding resistance.

Browser processes must be isolated from host services, credentials, and filesystem. Restrict response size, total transferred bytes, navigation duration, pages, and concurrency. Do not log full captured personal content. Partial capture records missing evidence instead of inferring success. No form submission, authentication, tracking, outreach, or publication is in scope.

Every database query and artifact request requires tenant authorization. Preview routes require authentication and emit noindex. Object storage is private; authorize access before issuing short-lived URLs. A preview acceptance records a review decision; it does not deploy a public site. Website content cannot modify agent instructions or introduce code, scripts, dependencies, credentials, or unsupported citations.

Retention is an operational policy, not an implicit guarantee: configure expiry, periodically remove objects and associated rows, and verify deletion logs. Local development does not provide a compliance certification or production penetration test. Review deployed network policy, authentication, backup retention, and storage access before using real client data.

## Implemented boundaries and remaining validation

Compose places the browser on an internal network, with only the validating proxy providing public egress. The proxy checks all DNS answers and connects to an approved literal IP. IPv6 transition destinations and multicast are rejected. Browser routes reject non-GET/HEAD requests, unsupported schemes, media and WebSockets, cap subrequests at 100 per viewport, disable service workers, and close popup pages. Proxy streams have a 20 MB limit per direction per connection and a 60 second connection deadline. Navigation is capped at 20 seconds. This is a bounded single-host design, not a completed penetration test.

Desktop/mobile viewports are fixed at 1440×1000 and 390×844, with UTC timezone, en-US locale and scale factor 1. The capture service has one semaphore slot and container memory/process limits. Browser credentials are a separate service key; model and storage secrets are held by the trusted worker. API tenant keys map to independent safe tenant identifiers. Artifact access is authorized on every request rather than using public storage URLs.

## Retention and deletion

Default retention policy is 30 days for terminal/review jobs, enforced when the operator runs the cleanup command. No automatic expiry scheduler is configured:

```sh
docker compose --env-file .env -f infra/compose.yaml exec worker python -m siteproof.retention --days 30
docker compose --env-file .env -f infra/compose.yaml exec worker python -m siteproof.retention --days 30 --apply
```

The first command lists candidates; `--apply` deletes them. `DELETE /api/jobs/{id}` permits explicit tenant-authorized deletion of inactive jobs. Active jobs must be cancelled first. Cleanup holds the worker's tenant/domain locks, removes storage objects and checkpoint data, removes fact retrieval chunks/rows, and clears the tenant embedding cache. Storage errors retain database references so cleanup can be retried. Backups and provider-side retention require separate operator policy. Only deletion guard tests ran locally; live PostgreSQL/MinIO deletion has not been verified.
