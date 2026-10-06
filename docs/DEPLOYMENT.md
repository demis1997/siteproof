# Deployment and operations

Use the root README for exact Compose commands and environment names. The first deployment is a private single-host development environment. Production requires TLS, strong authentication, private storage, restricted egress, secret management, backups, expiry cleanup, and an explicit domain allow/deny policy.

Do not expose PostgreSQL, Redis, MinIO administration, worker ports, or unauthenticated previews publicly. Health reports process availability; readiness must check required dependencies. Track a correlation ID from API request through queue job, checkpoint and model run. Retry transient failures with bounded exponential backoff and jitter; permanent URL or schema errors should fail immediately. Exhausted tasks belong in a dead-letter record for inspection.

Restart recovery must be tested using a persisted checkpoint and an interrupted worker, not inferred from the presence of a checkpoint library. Reconcile stale leases and preserve idempotency keys on requeue. Cancellation must be checked between stages and terminate active capture with cleanup.

Horizontal workers require distributed leases and shared concurrency limits. Single-host tests do not establish throughput or scalability. Measure p50/p95 latency and memory under representative load before making capacity claims.

Queue delivery uses a PostgreSQL transactional outbox and Redis AOF. Worker completion is idempotent by checkpoint thread and redesign revision; stale redesign deliveries are discarded. In-memory checkpoint resume and outbox mocks have passed; real process kill/restart recovery has not been measured. Single-host mode uses one workflow worker, one browser slot and tenant/domain Redis locks. Horizontal workers need processing ownership/leases and crash-recovery coordination before adding replicas; no scalability claim is made.
