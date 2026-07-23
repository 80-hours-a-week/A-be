// U15 trends mock state (BR-U5-19 mock-first parity). Follows + digest settings are
// owner-scoped server rows in real mode; the mock mirrors them with localStorage-backed
// state (the onboardingFixtures pattern) so follows/opt-in survive reloads and the
// desktop phone-preview iframe in mock mode. Validation mirrors the backend boundary
// exactly: DTO bounds → 422, cap/duplicate state conflicts → 409, bad token → 400.
import type {
  DigestCadence,
  DigestSettingsVM,
  FollowedTopicVM,
  FollowListVM,
} from '@/types/trends';
import { MAX_FOLLOWED_TOPICS, MAX_TOPIC_LENGTH } from '@/types/trends';

const FOLLOWS_KEY = 'docsuri-mock-trends-follows';
const SETTINGS_KEY = 'docsuri-mock-trends-settings';

/** Mock-valid unsubscribe token prefix — the real token is HMAC-signed per recipient;
 * the mock accepts this well-known prefix (demoable via /unsubscribe?token=mock-unsub-demo)
 * and rejects everything else with 400, mirroring the fail-closed contract (BR-TN4). */
export const MOCK_UNSUBSCRIBE_TOKEN_PREFIX = 'mock-unsub-';
export const MOCK_UNSUBSCRIBE_TOKEN = 'mock-unsub-token';

interface MockDigestSettings {
  optedIn: boolean;
  cadence: DigestCadence;
}

// Fallback when localStorage is unavailable (SSR / private mode) — same pattern as
// onboardingFixtures' mock state.
let memoryFollows: FollowedTopicVM[] = [];
let memorySettings: MockDigestSettings = { optedIn: false, cadence: 'daily' };

function isFollowedTopic(value: unknown): value is FollowedTopicVM {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === 'string' &&
    typeof record.topic === 'string' &&
    typeof record.createdAt === 'string'
  );
}

function readFollows(): FollowedTopicVM[] {
  if (typeof window === 'undefined') return memoryFollows;
  try {
    const raw = window.localStorage.getItem(FOLLOWS_KEY);
    if (!raw) return memoryFollows;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isFollowedTopic) : memoryFollows;
  } catch {
    return memoryFollows;
  }
}

function writeFollows(next: FollowedTopicVM[]): void {
  memoryFollows = next;
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(FOLLOWS_KEY, JSON.stringify(next));
  } catch {
    // localStorage unavailable — the in-memory fallback still holds the state.
  }
}

function readSettings(): MockDigestSettings {
  if (typeof window === 'undefined') return memorySettings;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return memorySettings;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return memorySettings;
    const record = parsed as Record<string, unknown>;
    const cadence = record.cadence === 'weekly' ? 'weekly' : 'daily';
    return { optedIn: record.optedIn === true, cadence };
  } catch {
    return memorySettings;
  }
}

function writeSettings(next: MockDigestSettings): void {
  memorySettings = next;
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  } catch {
    // ignore — memory fallback already updated.
  }
}

export function resetMockTrends(): void {
  memoryFollows = [];
  memorySettings = { optedIn: false, cadence: 'daily' };
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(FOLLOWS_KEY);
    window.localStorage.removeItem(SETTINGS_KEY);
  } catch {
    // ignore — memory fallback already reset.
  }
}

/** Test convenience — pre-populate the follow list (e.g. to exercise the 10-topic cap). */
export function seedMockFollows(topics: string[]): void {
  writeFollows(
    topics.map((topic, index) => ({
      id: `seed-follow-${index + 1}`,
      topic,
      createdAt: '2026-07-01T00:00:00Z',
    })),
  );
}

function followList(topics: FollowedTopicVM[]): FollowListVM {
  return { topics, maxTopics: MAX_FOLLOWED_TOPICS };
}

export function mockListFollows(): FollowListVM {
  return followList(readFollows());
}

/** Mirrors the backend boundary: DTO bounds (blank / over-length) → 422, per-user cap and
 * casefold duplicates → 409 — with the same English detail strings as the real controller
 * so the ApiClient's 409 mapping is exercised identically in mock and real mode. */
export function mockFollowTopic(body: unknown): {
  status: number;
  body: FollowedTopicVM | { detail: string };
} {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const raw = typeof record.topic === 'string' ? record.topic : '';
  if (raw.length === 0 || raw.length > MAX_TOPIC_LENGTH) {
    return { status: 422, body: { detail: 'topic length out of bounds' } };
  }
  const cleaned = raw.trim().split(/\s+/).join(' ');
  if (!cleaned) {
    return { status: 422, body: { detail: 'topic must not be blank' } };
  }
  const existing = readFollows();
  if (existing.some((row) => row.topic.toLowerCase() === cleaned.toLowerCase())) {
    return { status: 409, body: { detail: 'topic already followed' } };
  }
  if (existing.length >= MAX_FOLLOWED_TOPICS) {
    return {
      status: 409,
      body: { detail: `follow limit reached (max ${MAX_FOLLOWED_TOPICS})` },
    };
  }
  const created: FollowedTopicVM = {
    id: `follow-${Date.now()}-${existing.length + 1}`,
    topic: cleaned,
    createdAt: new Date().toISOString(),
  };
  writeFollows([...existing, created]);
  return { status: 201, body: created };
}

/** Owner-scoped delete — unknown id → null (the controller 404s). Returns the updated
 * list on success (the real DELETE responds with FollowListResponse). */
export function mockUnfollowTopic(topicId: string): FollowListVM | null {
  const existing = readFollows();
  const next = existing.filter((row) => row.id !== topicId);
  if (next.length === existing.length) return null;
  writeFollows(next);
  return followList(next);
}

export function mockGetDigestSettings(): DigestSettingsVM {
  const settings = readSettings();
  return { optedIn: settings.optedIn, cadence: settings.cadence, lastSentAt: null };
}

/** Mirrors DigestSettingsUpdate (strict DTO): non-boolean optedIn / unknown cadence → 422. */
export function mockPutDigestSettings(body: unknown): {
  status: number;
  body: DigestSettingsVM | { detail: string };
} {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  if (typeof record.optedIn !== 'boolean') {
    return { status: 422, body: { detail: 'optedIn must be a boolean' } };
  }
  const cadence = record.cadence ?? 'daily';
  if (cadence !== 'daily' && cadence !== 'weekly') {
    return { status: 422, body: { detail: 'cadence must be daily or weekly' } };
  }
  writeSettings({ optedIn: record.optedIn, cadence });
  return { status: 200, body: mockGetDigestSettings() };
}

/** No-login one-click opt-out (BR-TN4) — any token outside the mock-valid prefix is a 400
 * (the real path never 5xxes; every failure is "invalid unsubscribe token"). */
export function mockUnsubscribe(body: unknown): {
  status: number;
  body: { optedIn: boolean } | { detail: string };
} {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const token = typeof record.token === 'string' ? record.token : '';
  if (!token.startsWith(MOCK_UNSUBSCRIBE_TOKEN_PREFIX)) {
    return { status: 400, body: { detail: 'invalid unsubscribe token' } };
  }
  const settings = readSettings();
  writeSettings({ ...settings, optedIn: false });
  return { status: 200, body: { optedIn: false } };
}
