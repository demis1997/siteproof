CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS tenants (id text PRIMARY KEY, name text NOT NULL);
INSERT INTO tenants VALUES ('local', 'Local development') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS audit_jobs (
 id text PRIMARY KEY, tenant_id text NOT NULL REFERENCES tenants(id), idempotency_key text NOT NULL,
 submitted_url text NOT NULL, canonical_url text NOT NULL, status text NOT NULL DEFAULT 'queued', stage text NOT NULL DEFAULT 'queued',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 data jsonb NOT NULL DEFAULT '{}', retry_count integer NOT NULL DEFAULT 0, error jsonb,
 UNIQUE(tenant_id,idempotency_key));
CREATE TABLE IF NOT EXISTS records (
 id text PRIMARY KEY, tenant_id text NOT NULL REFERENCES tenants(id), job_id text REFERENCES audit_jobs(id) ON DELETE CASCADE,
 kind text NOT NULL CHECK(kind IN ('Capture','Evidence','BusinessFact','Finding','Redesign','VerificationResult','ModelRun','ReviewDecision')),
 data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS records_tenant_job ON records(tenant_id,job_id,kind);
CREATE TABLE IF NOT EXISTS knowledge_documents (
 id text PRIMARY KEY, tenant_id text NOT NULL REFERENCES tenants(id), collection text NOT NULL, source text NOT NULL,
 retrieved_at timestamptz NOT NULL DEFAULT now(), version text NOT NULL, reuse_notes text NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
 id text PRIMARY KEY, tenant_id text NOT NULL REFERENCES tenants(id), document_id text REFERENCES knowledge_documents(id),
 content text NOT NULL, content_hash text NOT NULL, embedding vector(1536),
 search tsvector GENERATED ALWAYS AS (to_tsvector('english',content)) STORED);
CREATE INDEX IF NOT EXISTS chunks_search ON knowledge_chunks USING gin(search);
CREATE TABLE IF NOT EXISTS embedding_cache (content_hash text NOT NULL, model text NOT NULL, embedding vector(1536), PRIMARY KEY(content_hash,model));
CREATE UNIQUE INDEX IF NOT EXISTS audit_jobs_tenant_id ON audit_jobs(tenant_id,id);
DO $$ BEGIN
 ALTER TABLE records ADD CONSTRAINT records_job_tenant FOREIGN KEY(tenant_id,job_id) REFERENCES audit_jobs(tenant_id,id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_docs_tenant_id ON knowledge_documents(tenant_id,id);
DO $$ BEGIN
 ALTER TABLE knowledge_chunks ADD CONSTRAINT chunks_document_tenant FOREIGN KEY(tenant_id,document_id) REFERENCES knowledge_documents(tenant_id,id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS job_id text;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_model text;
ALTER TABLE embedding_cache ADD COLUMN IF NOT EXISTS tenant_id text NOT NULL DEFAULT 'local' REFERENCES tenants(id);
ALTER TABLE embedding_cache DROP CONSTRAINT IF EXISTS embedding_cache_pkey;
ALTER TABLE embedding_cache ADD PRIMARY KEY(tenant_id,content_hash,model);
DO $$ BEGIN
 ALTER TABLE knowledge_documents ADD CONSTRAINT knowledge_job_tenant FOREIGN KEY(tenant_id,job_id) REFERENCES audit_jobs(tenant_id,id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS task_outbox (
 id bigserial PRIMARY KEY, tenant_id text NOT NULL REFERENCES tenants(id), job_id text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), dispatched_at timestamptz,
 FOREIGN KEY(tenant_id,job_id) REFERENCES audit_jobs(tenant_id,id) ON DELETE CASCADE);
