import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TrendsSettingsSection } from '@/components/mypage/TrendsSettingsSection';
import { resetMockTrends, seedMockFollows, mockGetDigestSettings } from '@/mocks/trendsFixtures';
import { ApiClient } from '@/lib/api/apiClient';

// U15 TrendsSettingsSection — 팔로우 주제 관리 + 이메일 다이제스트 옵트인 (US-TN1/TN2).
// Runs against the mock transport (localStorage-backed fixtures mirroring the backend
// boundary: 409 cap/duplicate, 422 bounds), like the other mypage/settings tests.

beforeEach(() => {
  window.localStorage.clear();
  resetMockTrends();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TrendsSettingsSection (U15)', () => {
  it('renders the empty follow list and adds a topic', async () => {
    render(<TrendsSettingsSection />);

    expect(await screen.findByTestId('trends-follows')).toBeInTheDocument();
    expect(screen.getByTestId('trends-follow-empty')).toBeInTheDocument();

    await userEvent.type(screen.getByTestId('trends-follow-input'), '  diffusion   models ');
    await userEvent.click(screen.getByTestId('trends-follow-submit'));

    // Whitespace is collapsed exactly like the backend DTO validator.
    await waitFor(() => expect(screen.getByText('diffusion models')).toBeInTheDocument());
    expect(screen.getByTestId('trends-follow-input')).toHaveValue('');
    expect(screen.queryByTestId('trends-follow-empty')).not.toBeInTheDocument();
  });

  it('deletes a followed topic', async () => {
    seedMockFollows(['retrieval augmentation']);
    render(<TrendsSettingsSection />);

    expect(await screen.findByText('retrieval augmentation')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '삭제' }));

    await waitFor(() =>
      expect(screen.queryByText('retrieval augmentation')).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId('trends-follow-empty')).toBeInTheDocument();
  });

  it('surfaces the 10-topic cap inline without calling the API', async () => {
    seedMockFollows(Array.from({ length: 10 }, (_, i) => `topic ${i + 1}`));
    const followSpy = vi.spyOn(ApiClient.prototype, 'followTopic');
    render(<TrendsSettingsSection />);

    expect(await screen.findByText('topic 10')).toBeInTheDocument();
    await userEvent.type(screen.getByTestId('trends-follow-input'), 'one too many');
    await userEvent.click(screen.getByTestId('trends-follow-submit'));

    expect(screen.getByTestId('trends-follow-error')).toHaveTextContent(
      '팔로우 주제는 최대 10개까지 등록할 수 있어요.',
    );
    expect(followSpy).not.toHaveBeenCalled();
  });

  it('surfaces the duplicate-topic 409 from the API inline', async () => {
    seedMockFollows(['attention']);
    render(<TrendsSettingsSection />);

    expect(await screen.findByText('attention')).toBeInTheDocument();
    // Case-insensitive duplicate — passes the client checks, 409s at the (mock) backend.
    await userEvent.type(screen.getByTestId('trends-follow-input'), 'Attention');
    await userEvent.click(screen.getByTestId('trends-follow-submit'));

    await waitFor(() =>
      expect(screen.getByTestId('trends-follow-error')).toHaveTextContent(
        '이미 팔로우한 주제예요.',
      ),
    );
  });

  it('defaults the digest opt-in to OFF and reveals cadence only when opted in', async () => {
    render(<TrendsSettingsSection />);

    const toggle = await screen.findByTestId('trends-digest-opt-in');
    expect(toggle).not.toBeChecked();
    expect(screen.queryByTestId('trends-digest-cadence')).not.toBeInTheDocument();

    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    const cadence = screen.getByTestId('trends-digest-cadence');
    expect(cadence).toHaveValue('daily');

    await userEvent.selectOptions(cadence, 'weekly');
    await waitFor(() => expect(cadence).toHaveValue('weekly'));
    expect(mockGetDigestSettings()).toMatchObject({ optedIn: true, cadence: 'weekly' });

    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(screen.queryByTestId('trends-digest-cadence')).not.toBeInTheDocument();
  });

  it('isolates a load failure to an inline retryable error (fail-soft)', async () => {
    vi.spyOn(ApiClient.prototype, 'listFollowedTopics').mockRejectedValueOnce(
      new Error('network down'),
    );
    render(<TrendsSettingsSection />);

    expect(await screen.findByTestId('trends-settings-error')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByTestId('trends-follows')).toBeInTheDocument();
  });
});
