'use client';

// InterestPickerModal (U14, US-OB1/OB2) — the onboarding interest picker as a modal
// overlay (the app's interstitial pattern — see SummaryModal). Renders the server-sent
// category whitelist as tappable multi-select chips; ORCID-derived suggestions (US-OB4)
// pre-highlight categories and appear as pre-checked, removable keyword chips.
//
// Fail-soft by design (BR-OB1): submit failure → inline retryable error (never a dead
// end); skip is fire-and-forget and always dismisses; Escape/backdrop dismiss locally
// without recording (status stays server-owned `pending`, so the user is re-prompted
// next session instead of being mis-marked as skipped — BR-OB4).
//
// Accessibility: role="dialog" aria-modal, Escape + backdrop close, initial focus,
// body-scroll lock while open (mirrors SummaryModal).
import { useEffect, useRef, useState } from 'react';
import { getApiClient, UserFacingError } from '@/lib/api';
import type { OrcidSuggestion } from '@/types/onboarding';
import styles from './InterestPickerModal.module.css';

interface InterestPickerModalProps {
  /** Allowed picker categories (whitelist from GET /onboarding/status). */
  categories: string[];
  /** ORCID-derived proposals — empty for the plain picker path. */
  suggestions: OrcidSuggestion[];
  /** Called when the picker is done (submitted / skipped / locally dismissed). */
  onDone: () => void;
}

// Korean labels for the C-6 corpus slice; unknown ids fall back to the raw arXiv id
// (the server whitelist is the SSOT — new categories still render).
const CATEGORY_LABELS: Record<string, string> = {
  'cs.AI': '인공지능',
  'cs.CL': '자연어 처리',
  'cs.CV': '컴퓨터 비전',
  'cs.LG': '머신러닝',
  'stat.ML': '통계적 머신러닝',
};

function toggled(set: ReadonlySet<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function InterestPickerModal({ categories, suggestions, onDone }: InterestPickerModalProps) {
  // Pre-highlight ORCID-suggested categories (whitelist-only) and pre-check the
  // suggested keywords; both stay user-editable (BR-OB3 — explicit approval on submit).
  const [selected, setSelected] = useState<ReadonlySet<string>>(
    () =>
      new Set(
        suggestions
          .filter((s) => s.kind === 'category' && categories.includes(s.value))
          .map((s) => s.value),
      ),
  );
  const [keywords, setKeywords] = useState<ReadonlySet<string>>(
    () => new Set(suggestions.filter((s) => s.kind === 'keyword').map((s) => s.value)),
  );
  const suggestedKeywords = suggestions.filter((s) => s.kind === 'keyword').map((s) => s.value);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const emptySelection = selected.size === 0 && keywords.size === 0;

  // Escape to dismiss (local only — see header comment) + body-scroll lock while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDone();
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onDone]);

  const onSubmit = async () => {
    if (submitting || emptySelection) return;
    setError(null);
    setSubmitting(true);
    try {
      // Manual picks keep source 'onboarding_picker'; accepted ORCID keywords ride in
      // keywords[] (BR-OB3 — recorded only through this explicit approval).
      await getApiClient().submitOnboardingInterests({
        categories: [...selected],
        keywords: [...keywords],
        source: 'onboarding_picker',
      });
      onDone();
    } catch (err) {
      setError(
        err instanceof UserFacingError ? err.message : '저장에 실패했습니다. 다시 시도해 주세요.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const onSkip = () => {
    // Fire-and-forget (BR-OB1: skip never blocks): dismiss immediately; a failed skip
    // just leaves the server state pending → re-prompt next session, never an error.
    void getApiClient()
      .skipOnboarding()
      .catch(() => undefined);
    onDone();
  };

  return (
    <div className={styles.backdrop} onClick={onDone} data-testid="interest-picker-backdrop">
      <div
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label="관심 분야 선택"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        data-testid="interest-picker"
      >
        <h2 className={styles.heading}>관심 분야를 알려주세요</h2>
        <p className={styles.helper}>검색 결과가 처음부터 관심사에 맞게 정렬돼요.</p>

        <section className={styles.section} aria-label="관심 분야">
          <ul className={styles.chipList}>
            {categories.map((cat) => (
              <li key={cat}>
                <button
                  type="button"
                  className={selected.has(cat) ? styles.chipActive : styles.chip}
                  aria-pressed={selected.has(cat)}
                  onClick={() => setSelected((prev) => toggled(prev, cat))}
                  data-testid={`interest-category-${cat}`}
                >
                  {CATEGORY_LABELS[cat] ?? cat}
                  <span className={styles.chipId}>{cat}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {suggestedKeywords.length > 0 ? (
          <section className={styles.section} aria-label="ORCID 추천 키워드">
            <h3 className={styles.sectionTitle}>ORCID 저작에서 찾은 키워드</h3>
            <p className={styles.sectionHelper}>탭해서 뺄 수 있어요.</p>
            <ul className={styles.chipList}>
              {suggestedKeywords.map((keyword) => (
                <li key={keyword}>
                  <button
                    type="button"
                    className={keywords.has(keyword) ? styles.chipActive : styles.chip}
                    aria-pressed={keywords.has(keyword)}
                    onClick={() => setKeywords((prev) => toggled(prev, keyword))}
                    data-testid={`interest-keyword-${keyword}`}
                  >
                    {keyword}
                    {keywords.has(keyword) ? (
                      <span className={styles.chipRemove} aria-hidden="true">
                        ✕
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {error ? (
          <p className={styles.error} role="alert" data-testid="interest-picker-error">
            {error}
          </p>
        ) : null}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.skip}
            onClick={onSkip}
            data-testid="interest-picker-skip"
          >
            건너뛰기
          </button>
          <button
            type="button"
            className={styles.submit}
            onClick={() => void onSubmit()}
            disabled={emptySelection || submitting}
            data-testid="interest-picker-submit"
          >
            {submitting ? '저장 중…' : '저장하기'}
          </button>
        </div>
      </div>
    </div>
  );
}
