import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlanSection } from '@/components/mypage/PlanSection';
import { resetMockPlan, setMockPlanTier } from '@/mocks/planFixtures';
import { ApiClient } from '@/lib/api/apiClient';

// U16 PlanSection — 현재 티어 · 오늘의 에이전트 쿼터 · (plus) 만료일 (US-SB1). Runs
// against the mock transport like the other mypage/settings tests. C-12: the section is
// read-only — no payment/upgrade control may ever render, which the last test pins down.

beforeEach(() => {
  resetMockPlan();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PlanSection (U16)', () => {
  it('renders the free tier with the free daily quotas and no expiry', async () => {
    render(<PlanSection />);

    expect(await screen.findByTestId('plan-section')).toBeInTheDocument();
    expect(screen.getByTestId('plan-tier-badge')).toHaveTextContent('Free');
    expect(screen.getByTestId('plan-quota-evidence')).toHaveTextContent('하루 30회');
    expect(screen.getByTestId('plan-quota-novelty')).toHaveTextContent('하루 5회');
    expect(screen.queryByTestId('plan-expires')).not.toBeInTheDocument();
  });

  it('renders the plus tier with the boosted quotas and the expiry date', async () => {
    setMockPlanTier('plus');
    render(<PlanSection />);

    expect(await screen.findByTestId('plan-tier-badge')).toHaveTextContent('Plus');
    expect(screen.getByTestId('plan-quota-evidence')).toHaveTextContent('하루 90회');
    expect(screen.getByTestId('plan-quota-novelty')).toHaveTextContent('하루 15회');
    expect(screen.getByTestId('plan-expires')).toHaveTextContent('2026-08-15까지');
  });

  it('degrades quietly to the free defaults when /plans/me fails (BR-SB5 mirror)', async () => {
    vi.spyOn(ApiClient.prototype, 'getMyPlan').mockRejectedValueOnce(new Error('network down'));
    render(<PlanSection />);

    expect(await screen.findByTestId('plan-section')).toBeInTheDocument();
    expect(screen.getByTestId('plan-tier-badge')).toHaveTextContent('Free');
    expect(screen.getByTestId('plan-quota-evidence')).toHaveTextContent('하루 30회');
    expect(screen.getByTestId('plan-quota-novelty')).toHaveTextContent('하루 5회');
    // 조용한 강등 — 오류 배너도 재시도 버튼도 없이 free 기본값만 보인다.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders no payment or upgrade controls (C-12)', async () => {
    render(<PlanSection />);

    const section = await screen.findByTestId('plan-section');
    expect(section.querySelector('button')).toBeNull();
    expect(section.querySelector('a')).toBeNull();
  });
});
