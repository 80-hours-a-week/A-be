// U15 Trends/Notifications — hand-authored VM types mirroring backend/modules/trends/models.py
// (FollowedTopicResponse / FollowListResponse / DigestSettingsResponse / UnsubscribeResponse),
// pending shared-schema promotion + codegen — same status as onboarding.ts / personalization.ts.

export type DigestCadence = 'daily' | 'weekly';

/** Public projection of a followed topic (the embedding is internal and never serialized). */
export interface FollowedTopicVM {
  id: string;
  topic: string;
  createdAt: string;
}

export interface FollowListVM {
  topics: FollowedTopicVM[];
  /** Server product bound (models.MAX_TOPICS_PER_USER) — rides along so the FE cap mirrors it. */
  maxTopics: number;
}

export interface DigestSettingsVM {
  /** BR-TN1 — default false: no digest is ever sent before the user opts in. */
  optedIn: boolean;
  cadence: DigestCadence;
  lastSentAt: string | null;
}

export interface UnsubscribeResultVM {
  optedIn: boolean;
}

// Client-side mirrors of the backend DTO bounds (models.MAX_TOPICS_PER_USER /
// MAX_TOPIC_LENGTH) — UX aid only; the backend stays authoritative (409/422).
export const MAX_FOLLOWED_TOPICS = 10;
export const MAX_TOPIC_LENGTH = 120;
