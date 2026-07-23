import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Controllable ApiClient stub (same pattern as saveToLibrary.test.tsx) so every branch of
// the fail-soft contract (BR-OB1/US-OB4) is scriptable: pending/completed status, status
// failure, ORCID suggestions present/failed, submit failure+retry. UserFacingError is
// re-exported from the real module — the picker's error path instanceof-checks it.
const getOnboardingStatus = vi.fn();
const submitOnboardingInterests = vi.fn();
const skipOnboarding = vi.fn();
const getOrcidOnboardingSuggestions = vi.fn();
const currentSession = vi.fn();
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    getApiClient: () => ({
      getOnboardingStatus,
      submitOnboardingInterests,
      skipOnboarding,
      getOrcidOnboardingSuggestions,
      currentSession,
    }),
  };
});

import { OnboardingGate } from '@/components/onboarding/OnboardingGate';
import { SessionProvider } from '@/components/session/SessionContext';

const CATEGORIES = ['cs.AI', 'cs.CL', 'cs.CV', 'cs.LG', 'stat.ML'];

function renderGate() {
  return render(
    <SessionProvider>
      <OnboardingGate />
    </SessionProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  currentSession.mockResolvedValue({
    userId: 'user_ob_test',
    expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
  });
  getOnboardingStatus.mockResolvedValue({ state: 'pending', categories: CATEGORIES });
  getOrcidOnboardingSuggestions.mockResolvedValue({ suggestions: [], degraded: false });
  submitOnboardingInterests.mockResolvedValue({
    state: 'completed',
    eventRecorded: true,
    reason: 'recorded',
  });
  skipOnboarding.mockResolvedValue({ state: 'skipped' });
});

describe('OnboardingGate + InterestPickerModal', () => {
  it('renders the category chips on pending and disables submit while nothing is selected', async () => {
    renderGate();

    expect(await screen.findByTestId('interest-picker')).toBeInTheDocument();
    expect(screen.getByText('관심 분야를 알려주세요')).toBeInTheDocument();
    for (const cat of CATEGORIES) {
      expect(screen.getByTestId(`interest-category-${cat}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId('interest-picker-submit')).toBeDisabled();
  });

  it('submits the selection with source onboarding_picker and dismisses', async () => {
    const user = userEvent.setup();
    renderGate();

    await user.click(await screen.findByTestId('interest-category-cs.AI'));
    const submit = screen.getByTestId('interest-picker-submit');
    expect(submit).not.toBeDisabled();
    await user.click(submit);

    await waitFor(() =>
      expect(submitOnboardingInterests).toHaveBeenCalledWith({
        categories: ['cs.AI'],
        keywords: [],
        source: 'onboarding_picker',
      }),
    );
    await waitFor(() => expect(screen.queryByTestId('interest-picker')).not.toBeInTheDocument());
  });

  it('건너뛰기 calls POST /onboarding/skip and dismisses', async () => {
    const user = userEvent.setup();
    renderGate();

    await user.click(await screen.findByTestId('interest-picker-skip'));

    expect(skipOnboarding).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByTestId('interest-picker')).not.toBeInTheDocument());
  });

  it('renders nothing when status is not pending (BR-OB4 — zero friction)', async () => {
    getOnboardingStatus.mockResolvedValue({ state: 'completed', categories: CATEGORIES });
    renderGate();

    await waitFor(() => expect(getOnboardingStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('interest-picker')).not.toBeInTheDocument();
  });

  it('renders nothing (no crash) when the status fetch fails (BR-OB1 fail-soft)', async () => {
    getOnboardingStatus.mockRejectedValue(new Error('gateway down'));
    renderGate();

    await waitFor(() => expect(getOnboardingStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('interest-picker')).not.toBeInTheDocument();
  });

  it('pre-highlights ORCID suggestions and submits accepted keywords in keywords[]', async () => {
    getOrcidOnboardingSuggestions.mockResolvedValue({
      suggestions: [
        { kind: 'category', value: 'cs.LG' },
        { kind: 'keyword', value: 'attention mechanism' },
        { kind: 'keyword', value: 'diffusion models' },
      ],
      degraded: false,
    });
    const user = userEvent.setup();
    renderGate();

    // Suggested category pre-selected, keywords pre-checked (removable).
    const suggested = await screen.findByTestId('interest-category-cs.LG');
    expect(suggested).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('interest-keyword-attention mechanism')).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    // Remove one keyword, then submit — source stays onboarding_picker (manual approval).
    await user.click(screen.getByTestId('interest-keyword-diffusion models'));
    await user.click(screen.getByTestId('interest-picker-submit'));

    await waitFor(() =>
      expect(submitOnboardingInterests).toHaveBeenCalledWith({
        categories: ['cs.LG'],
        keywords: ['attention mechanism'],
        source: 'onboarding_picker',
      }),
    );
  });

  it('falls back to the plain picker when the ORCID suggestion fetch fails (US-OB4)', async () => {
    getOrcidOnboardingSuggestions.mockRejectedValue(new Error('orcid down'));
    renderGate();

    expect(await screen.findByTestId('interest-picker')).toBeInTheDocument();
    expect(screen.queryByText('ORCID 저작에서 찾은 키워드')).not.toBeInTheDocument();
  });

  it('shows a retryable inline error when submit fails instead of dismissing', async () => {
    submitOnboardingInterests.mockRejectedValueOnce(new Error('network'));
    const user = userEvent.setup();
    renderGate();

    await user.click(await screen.findByTestId('interest-category-cs.AI'));
    await user.click(screen.getByTestId('interest-picker-submit'));

    expect(await screen.findByTestId('interest-picker-error')).toBeInTheDocument();
    expect(screen.getByTestId('interest-picker')).toBeInTheDocument(); // still open — retryable

    await user.click(screen.getByTestId('interest-picker-submit')); // retry → succeeds
    await waitFor(() => expect(screen.queryByTestId('interest-picker')).not.toBeInTheDocument());
    expect(submitOnboardingInterests).toHaveBeenCalledTimes(2);
  });
});
