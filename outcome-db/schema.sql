-- outcome-db/schema.sql
-- PostgreSQL + pgvector schema for cross-factory outcome insights
-- Sprint M1: tables exist but writable=False enforced at application layer
-- Reference: POLICIES.md + AI Builder's Handbook Cap 14 §14.7
--
-- Prerequisites:
--   CREATE EXTENSION IF NOT EXISTS "pgcrypto";
--   CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- Extensions
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- Enums
-- ============================================================

DO $$ BEGIN
    CREATE TYPE confidence_level_enum AS ENUM (
        'anecdotal',
        'preliminary',
        'predictive'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 1. factories
-- ============================================================

CREATE TABLE IF NOT EXISTS factories (
    factory_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    vertical            TEXT NOT NULL,          -- e.g. "fintech", "edtech", "healthtech"
    owner_tenant_id     UUID NOT NULL,           -- maps to auth tenant; never exposed cross-factory
    first_active_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    operation_days      INT GENERATED ALWAYS AS (
                            EXTRACT(DAY FROM NOW() - first_active_at)::INT
                        ) STORED,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_factories_owner_tenant
    ON factories (owner_tenant_id);

CREATE INDEX IF NOT EXISTS idx_factories_vertical
    ON factories (vertical);

-- ============================================================
-- 2. outcome_insights
-- ============================================================

CREATE TABLE IF NOT EXISTS outcome_insights (
    insight_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id          UUID NOT NULL REFERENCES factories (factory_id) ON DELETE RESTRICT,
    content             TEXT NOT NULL,
    confidence_level    confidence_level_enum NOT NULL,
    source_data_points  INT NOT NULL CHECK (source_data_points >= 1),
    relevance_score     FLOAT NOT NULL DEFAULT 1.0
                            CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
    tags                TEXT[] NOT NULL DEFAULT '{}',
    cross_vertical      BOOLEAN NOT NULL DEFAULT FALSE,
    embedding           VECTOR(1536),            -- OpenAI / compatible 1536-dim embeddings
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ,             -- NULL = no TTL (PREDICTIVE only)
    archived_at         TIMESTAMPTZ,             -- populated by eviction cron
    orphaned            BOOLEAN NOT NULL DEFAULT FALSE,
    -- audit
    written_by_gate_version TEXT NOT NULL DEFAULT '1.0'
);

-- Index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_outcome_insights_embedding
    ON outcome_insights
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for expiry-based eviction queries
CREATE INDEX IF NOT EXISTS idx_outcome_insights_expires_at
    ON outcome_insights (expires_at)
    WHERE expires_at IS NOT NULL AND archived_at IS NULL;

-- Index for relevance score eviction queries
CREATE INDEX IF NOT EXISTS idx_outcome_insights_relevance
    ON outcome_insights (relevance_score, confidence_level)
    WHERE archived_at IS NULL;

-- Cross-vertical filter
CREATE INDEX IF NOT EXISTS idx_outcome_insights_cross_vertical
    ON outcome_insights (cross_vertical)
    WHERE cross_vertical = TRUE AND archived_at IS NULL;

-- Per-factory lookup
CREATE INDEX IF NOT EXISTS idx_outcome_insights_factory_id
    ON outcome_insights (factory_id);

-- ============================================================
-- 3. factory_access_log (audit trail)
-- ============================================================

CREATE TABLE IF NOT EXISTS factory_access_log (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id          UUID NOT NULL REFERENCES outcome_insights (insight_id) ON DELETE CASCADE,
    reader_factory_id   UUID NOT NULL REFERENCES factories (factory_id) ON DELETE CASCADE,
    accessed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Hash of the query that triggered the read (no raw query stored — privacy)
    query_context_hash  TEXT,
    -- Cross-tenant read? True when reader != insight.factory_id
    is_cross_tenant     BOOLEAN NOT NULL GENERATED ALWAYS AS (
                            reader_factory_id != (
                                SELECT factory_id FROM outcome_insights
                                WHERE outcome_insights.insight_id = factory_access_log.insight_id
                            )
                        ) STORED
);

CREATE INDEX IF NOT EXISTS idx_access_log_insight_id
    ON factory_access_log (insight_id);

CREATE INDEX IF NOT EXISTS idx_access_log_reader_factory
    ON factory_access_log (reader_factory_id);

CREATE INDEX IF NOT EXISTS idx_access_log_accessed_at
    ON factory_access_log (accessed_at DESC);

-- Cross-tenant reads only
CREATE INDEX IF NOT EXISTS idx_access_log_cross_tenant
    ON factory_access_log (is_cross_tenant)
    WHERE is_cross_tenant = TRUE;

-- ============================================================
-- 4. Row-Level Security (cross-tenant isolation)
-- ============================================================

-- Enable RLS on outcome_insights
ALTER TABLE outcome_insights ENABLE ROW LEVEL SECURITY;

-- Policy: a factory can read its own insights OR cross_vertical insights
-- The application sets: SET LOCAL app.current_factory_id = '<uuid>'
CREATE POLICY outcome_insights_tenant_isolation
    ON outcome_insights
    FOR SELECT
    USING (
        factory_id::TEXT = current_setting('app.current_factory_id', TRUE)
        OR cross_vertical = TRUE
    );

-- Inserts/updates are only allowed via service role (bypasses RLS by default)
-- Application layer (write_gate.py) enforces additional checks before reaching DB.

-- Enable RLS on factory_access_log
ALTER TABLE factory_access_log ENABLE ROW LEVEL SECURITY;

-- A factory can only read its own access log entries
CREATE POLICY factory_access_log_tenant_isolation
    ON factory_access_log
    FOR SELECT
    USING (
        reader_factory_id::TEXT = current_setting('app.current_factory_id', TRUE)
    );

-- ============================================================
-- 5. Eviction helper view
-- ============================================================

CREATE OR REPLACE VIEW insights_pending_eviction AS
SELECT
    insight_id,
    factory_id,
    confidence_level,
    relevance_score,
    expires_at,
    CASE
        WHEN expires_at IS NOT NULL AND expires_at < NOW() THEN 'ttl_expired'
        WHEN relevance_score < 0.3 THEN 'low_relevance'
        ELSE 'ok'
    END AS eviction_reason
FROM outcome_insights
WHERE archived_at IS NULL
  AND (
      (expires_at IS NOT NULL AND expires_at < NOW())
      OR relevance_score < 0.3
  );

-- ============================================================
-- 6. Trigger: auto-update updated_at on factories
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_factories_updated_at ON factories;
CREATE TRIGGER trg_factories_updated_at
    BEFORE UPDATE ON factories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
