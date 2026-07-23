-- U15 Trends/Notifications — followed topics, digest settings, send log (functional-design §1).
-- All rows owner-scoped (SEC-8). Follow topics are EXPLICIT user input — disjoint from the
-- U14/U9 interest tables by construction (BR-TN5: no FK, no shared rows, no cross reads).

-- Topic embedding is written ONCE at registration (same model/space as the corpus) and stored
-- in the row so the digest job never calls the embedding model (BR-TN7).
CREATE TABLE IF NOT EXISTS followed_topics (
    id         VARCHAR(36)  PRIMARY KEY,
    owner_id   VARCHAR(36)  NOT NULL,
    topic      VARCHAR(120) NOT NULL,
    embedding  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_followed_topics_owner
    ON followed_topics (owner_id, created_at ASC, id ASC);

-- last_sent_at = the send watermark (BR-TN2: empty digest never advances it).
-- updated_at bumps ONLY on user-visible settings changes — it versions the signed
-- unsubscribe token (settings change ⇒ outstanding tokens invalidated, SEC-8).
CREATE TABLE IF NOT EXISTS digest_settings (
    owner_id     VARCHAR(36) PRIMARY KEY,
    opted_in     BOOLEAN     NOT NULL DEFAULT FALSE,
    cadence      VARCHAR(16) NOT NULL DEFAULT 'daily',
    last_sent_at TIMESTAMPTZ,
    opted_in_at  TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL
);

-- One row per delivered digest (observability/idempotency). The email body is never stored.
CREATE TABLE IF NOT EXISTS digest_send_log (
    id          VARCHAR(36) PRIMARY KEY,
    owner_id    VARCHAR(36) NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL,
    paper_count INTEGER     NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_digest_send_log_owner_sent
    ON digest_send_log (owner_id, sent_at ASC, id ASC);
