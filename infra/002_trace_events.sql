-- Idempotent upgrade for existing single-host volumes; no data deletion.
ALTER TABLE records DROP CONSTRAINT IF EXISTS records_kind_check;
ALTER TABLE records ADD CONSTRAINT records_kind_check CHECK(kind IN ('Capture','Evidence','BusinessFact','Finding','Redesign','VerificationResult','ModelRun','ReviewDecision','TraceEvent'));
