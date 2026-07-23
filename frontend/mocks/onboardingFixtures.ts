// U14 onboarding mock state (BR-U5-19 mock-first parity). The real OnboardingStatus is
// server-owned per user (BR-OB4 re-prompt guard); the mock mirrors that with a
// localStorage-backed state (like the mock session) so completing/skipping never
// re-prompts across reloads or the desktop phone-preview iframe in mock mode.
import type {
  InterestsResult,
  OnboardingState,
  OnboardingStatusResponse,
  OrcidSuggestionsResponse,
  SkipResult,
} from '@/types/onboarding';
import { mockGetOrcidProfile } from './mypageFixtures';

// Mirrors backend ALLOWED_CATEGORIES (C-6 corpus slice — served by GET /onboarding/status).
export const MOCK_ONBOARDING_CATEGORIES: readonly string[] = [
  'cs.AI',
  'cs.CL',
  'cs.CV',
  'cs.LG',
  'stat.ML',
];

const STATE_KEY = 'docsuri-mock-onboarding-state';

// Fallback when localStorage is unavailable (SSR / private mode) — same pattern as
// accountFixtures' mock session.
let memoryState: OnboardingState = 'pending';

function isOnboardingState(value: unknown): value is OnboardingState {
  return value === 'pending' || value === 'completed' || value === 'skipped';
}

function readState(): OnboardingState {
  if (typeof window === 'undefined') return memoryState;
  try {
    const raw = window.localStorage.getItem(STATE_KEY);
    return isOnboardingState(raw) ? raw : memoryState;
  } catch {
    return memoryState;
  }
}

function writeState(next: OnboardingState): void {
  memoryState = next;
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STATE_KEY, next);
  } catch {
    // localStorage unavailable — the in-memory fallback still holds the state.
  }
}

export function resetMockOnboarding(): void {
  memoryState = 'pending';
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STATE_KEY);
  } catch {
    // ignore — memory fallback already reset.
  }
}

export function mockOnboardingStatus(): OnboardingStatusResponse {
  return { state: readState(), categories: [...MOCK_ONBOARDING_CATEGORIES] };
}

/** Mirrors the backend InterestSelection validation: empty selection / non-whitelist
 * category → 422 (the DTO boundary), otherwise state=completed + seed event recorded. */
export function mockSubmitInterests(body: unknown): {
  status: number;
  body: InterestsResult | { detail: string };
} {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const categories = Array.isArray(record.categories) ? record.categories.map(String) : [];
  const keywords = Array.isArray(record.keywords) ? record.keywords.map(String) : [];
  const unknown = categories.filter((cat) => !MOCK_ONBOARDING_CATEGORIES.includes(cat));
  if (unknown.length) {
    return {
      status: 422,
      body: { detail: `categories outside the corpus slice: ${unknown.join(', ')}` },
    };
  }
  if (!categories.length && !keywords.length) {
    return {
      status: 422,
      body: { detail: 'empty selection: pick at least one category or keyword' },
    };
  }
  writeState('completed');
  return { status: 200, body: { state: 'completed', eventRecorded: true, reason: 'recorded' } };
}

/** Idempotent skip — no event, no profile touch (BR-OB4). */
export function mockSkipOnboarding(): SkipResult {
  writeState('skipped');
  return { state: 'skipped' };
}

/** ORCID-derived proposals — present only when the mock account is ORCID-linked
 * (mypage fixture), empty (NOT degraded) otherwise, mirroring the real controller. */
export function mockOrcidSuggestions(): OrcidSuggestionsResponse {
  if (!mockGetOrcidProfile()) return { suggestions: [], degraded: false };
  return {
    suggestions: [
      { kind: 'category', value: 'cs.LG' },
      { kind: 'keyword', value: 'attention mechanism' },
      { kind: 'keyword', value: 'protein structure prediction' },
    ],
    degraded: false,
  };
}
