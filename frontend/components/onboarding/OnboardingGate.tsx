'use client';

// OnboardingGate (U14, US-OB1/OB2) — app-shell interstitial gate, mounted once in the
// root layout under SessionProvider. When the session becomes authenticated it fetches
// GET /onboarding/status ONCE per user; only `pending` surfaces the interest picker
// (BR-OB4 — `completed`/`skipped` add zero friction). Everything fails soft (BR-OB1):
// a status fetch error skips the prompt entirely, and ORCID suggestions are a
// best-effort enrichment — any failure or `degraded` falls back to the plain picker
// (US-OB4). The prompt decision is server-owned; the gate never persists anything.
import { useEffect, useRef, useState } from 'react';
import { getApiClient } from '@/lib/api';
import { useSession } from '@/components/session/SessionContext';
import type { OrcidSuggestion } from '@/types/onboarding';
import { InterestPickerModal } from './InterestPickerModal';

interface PickerPrompt {
  categories: string[];
  suggestions: OrcidSuggestion[];
}

export function OnboardingGate() {
  const { status, user } = useSession();
  const [prompt, setPrompt] = useState<PickerPrompt | null>(null);
  // One status check per authenticated user (keyed so logout → different login re-checks).
  const checkedFor = useRef<string | null>(null);

  useEffect(() => {
    if (status !== 'authenticated' || !user) return;
    if (checkedFor.current === user.userId) return;
    checkedFor.current = user.userId;
    let cancelled = false;
    void (async () => {
      try {
        const onboarding = await getApiClient().getOnboardingStatus();
        if (cancelled || onboarding.state !== 'pending') return;
        // Best-effort ORCID proposals — just attempt the call; a non-ORCID account
        // returns empty, and any failure degrades to the plain picker (US-OB4).
        let suggestions: OrcidSuggestion[] = [];
        try {
          const proposed = await getApiClient().getOrcidOnboardingSuggestions();
          if (!proposed.degraded) suggestions = proposed.suggestions;
        } catch {
          // picker-only fallback — never block or error-screen (BR-OB1).
        }
        if (!cancelled) setPrompt({ categories: onboarding.categories, suggestions });
      } catch {
        // Status unavailable → no prompt this session; login/signup is never blocked (BR-OB1).
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, user]);

  if (status !== 'authenticated' || !prompt) return null;
  return (
    <InterestPickerModal
      categories={prompt.categories}
      suggestions={prompt.suggestions}
      onDone={() => setPrompt(null)}
    />
  );
}
