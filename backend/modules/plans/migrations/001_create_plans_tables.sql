-- U16 Subscription/Plans — plan assignments + daily spend rollup (functional-design §1).
-- free = row ABSENCE (BR-SB1): no default rows, no backfill for existing users.

-- Append-only grant history: a revoke only MARKS revoked_at (paid-through-period, BR-SB2);
-- a re-grant inserts a fresh row. Activity is DERIVED (now() < expires_at on the latest
-- row) — no expiry job/scheduler exists (BR-SB2). expiry_noted_at is the idempotency
-- marker for the one-shot deferred expiry audit (BR-SB6).
CREATE TABLE IF NOT EXISTS plan_assignments (
    id              VARCHAR(36) PRIMARY KEY,
    user_id         VARCHAR(36) NOT NULL,
    tier            VARCHAR(16) NOT NULL DEFAULT 'plus',
    starts_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    granted_by      VARCHAR(36) NOT NULL,
    expiry_noted_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_plan_assignments_user_latest
    ON plan_assignments (user_id, starts_at DESC, created_at DESC, id DESC);

-- Observation-only per-user daily Bedrock spend (spend report recommendation #2): usd is
-- upsert-ADDED per (user, UTC date, module). Participates in NO enforcement (BR-SB7);
-- v1 has no user-facing API — operator SQL only.
CREATE TABLE IF NOT EXISTS user_daily_spend (
    user_id    VARCHAR(36)      NOT NULL,
    date       DATE             NOT NULL,
    module     VARCHAR(32)      NOT NULL,
    usd        DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (user_id, date, module)
);
