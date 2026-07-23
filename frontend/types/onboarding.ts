// U14 Onboarding — hand-authored VM types mirroring backend/modules/onboarding/models.py
// (OnboardingStatusResponse / InterestSelection / InterestsResult / SkipResult /
// OrcidSuggestionsResponse), pending shared-schema promotion + codegen — same status as
// personalization.ts / paperMeta.ts.

export type OnboardingState = 'pending' | 'completed' | 'skipped';

export interface OnboardingStatusResponse {
  state: OnboardingState;
  /** Allowed picker categories (server whitelist — anything outside it → 422). */
  categories: string[];
}

/** Picker selection (transient, request scope only — functional-design §1). */
export interface InterestSelectionCreate {
  categories: string[];
  keywords: string[];
  source: 'onboarding_picker' | 'orcid_derived';
}

export interface InterestsResult {
  state: OnboardingState;
  /** `false` + reason is the NFR-P4 degrade signal: state completed, seed event dropped. */
  eventRecorded: boolean;
  reason: 'recorded' | 'duplicate' | 'disabled' | 'degraded';
}

export interface SkipResult {
  state: OnboardingState;
}

export interface OrcidSuggestion {
  kind: 'category' | 'keyword';
  value: string;
}

export interface OrcidSuggestionsResponse {
  suggestions: OrcidSuggestion[];
  /** `true` means the ORCID lookup path failed — FE falls back to picker-only (US-OB4). */
  degraded: boolean;
}
