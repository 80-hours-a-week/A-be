// U16 plan mock state (BR-U5-19 mock-first parity). GET /plans/me is an owner-scoped
// read in real mode; the mock serves a module-level tier (memory-only — plus grants are
// ADMIN backend operations with no FE surface at all, C-12, so unlike trendsFixtures
// there is no user mutation to persist across reloads).
import type { MyPlanVM, PlanTier } from '@/types/plan';
import { FREE_PLAN_QUOTAS } from '@/types/plan';

/** Free tier — no PlanAssignment row (BR-SB1), so no expiresAt. Quotas mirror the
 * backend free env defaults (30/5). */
export const freePlanFixture: MyPlanVM = {
  tier: 'free',
  quotas: FREE_PLAN_QUOTAS,
};

/** Plus tier — 3× spend-report defaults (90/15) + the derived monthly expiry (BR-SB2). */
export const plusPlanFixture: MyPlanVM = {
  tier: 'plus',
  quotas: { evidenceDaily: 90, noveltyDaily: 15 },
  expiresAt: '2026-08-15T00:00:00Z',
};

let mockTier: PlanTier = 'free';

export function resetMockPlan(): void {
  mockTier = 'free';
}

/** Test/demo convenience — flip the mock user's tier (the real grant path is ADMIN-only
 * and never reachable from the FE, C-12). */
export function setMockPlanTier(tier: PlanTier): void {
  mockTier = tier;
}

export function mockGetMyPlan(): MyPlanVM {
  return mockTier === 'plus' ? plusPlanFixture : freePlanFixture;
}
