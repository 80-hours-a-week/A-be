-- U14 Onboarding — owner-scoped onboarding status (re-prompt guard, BR-OB4/SEC-8).
-- UI state only: 'skipped' leaves no trace in events or profiles (functional-design §1).

CREATE TABLE IF NOT EXISTS onboarding_status (
    owner_id    VARCHAR(36) PRIMARY KEY,
    state       VARCHAR(16) NOT NULL DEFAULT 'pending',
    prompted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
