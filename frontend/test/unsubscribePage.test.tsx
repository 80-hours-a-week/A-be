import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UnsubscribeDigest } from '@/components/UnsubscribeDigest';
import {
  MOCK_UNSUBSCRIBE_TOKEN,
  mockGetDigestSettings,
  mockPutDigestSettings,
  resetMockTrends,
} from '@/mocks/trendsFixtures';
import { ApiClient } from '@/lib/api/apiClient';

// U15 unsubscribe page (US-TN2, BR-TN4) — no-login one-click opt-out. Success and
// invalid-token paths both terminate on the page (never a redirect/login gate).

let search = '';
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  window.localStorage.clear();
  resetMockTrends();
  search = '';
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('UnsubscribeDigest (U15)', () => {
  it('confirms, POSTs the token, and shows the opted-out terminal state', async () => {
    // 옵트인된 수신자가 이메일 링크로 들어온 상황.
    mockPutDigestSettings({ optedIn: true, cadence: 'daily' });
    search = `token=${MOCK_UNSUBSCRIBE_TOKEN}`;
    render(<UnsubscribeDigest />);

    expect(screen.getByTestId('unsubscribe-confirm')).toHaveTextContent(
      '다이제스트 수신을 해지할까요?',
    );
    await userEvent.click(screen.getByTestId('unsubscribe-submit'));

    await waitFor(() =>
      expect(screen.getByTestId('unsubscribe-success')).toHaveTextContent('수신이 해지되었습니다'),
    );
    expect(mockGetDigestSettings().optedIn).toBe(false);
  });

  it('shows the invalid-link message on a bad token (400 — never a crash or redirect)', async () => {
    search = 'token=not-a-real-token';
    render(<UnsubscribeDigest />);

    await userEvent.click(screen.getByTestId('unsubscribe-submit'));

    await waitFor(() =>
      expect(screen.getByTestId('unsubscribe-error')).toHaveTextContent(
        '링크가 유효하지 않습니다.',
      ),
    );
  });

  it('treats a missing token as an invalid link without calling the API', () => {
    const unsubscribeSpy = vi.spyOn(ApiClient.prototype, 'unsubscribeDigest');
    render(<UnsubscribeDigest />);

    expect(screen.getByTestId('unsubscribe-error')).toHaveTextContent('링크가 유효하지 않습니다.');
    expect(unsubscribeSpy).not.toHaveBeenCalled();
  });
});
