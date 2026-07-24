// U16 Subscription/Plans — hand-authored VM types mirroring the GET /plans/me contract
// (backend U16 module, US-SB1), pending shared-schema promotion + codegen — same status
// as trends.ts / onboarding.ts / personalization.ts.

export type PlanTier = 'free' | 'plus';

/** Daily agent quotas the active plan supplies (BR-SB3 — values only; the limiter
 * enforcement mechanism is unchanged and backend-owned). */
export interface PlanQuotasVM {
  evidenceDaily: number;
  noveltyDaily: number;
}

export interface MyPlanVM {
  tier: PlanTier;
  quotas: PlanQuotasVM;
  /** Present only when tier === 'plus' — the derived paid-through expiry (BR-SB2). */
  expiresAt?: string;
}

// Client-side mirror of the backend free-tier defaults (DOCSURI_AGENT_EVIDENCE_DAILY_LIMIT=30 /
// DOCSURI_AGENT_NOVELTY_DAILY_LIMIT=5). Display fail-safe only, echoing BR-SB5 (plan
// resolution failure = free values): the backend stays authoritative.
export const FREE_PLAN_QUOTAS: PlanQuotasVM = { evidenceDaily: 30, noveltyDaily: 5 };
