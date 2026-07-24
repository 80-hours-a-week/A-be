'use client';

import { useEffect, useState } from 'react';
import { getApiClient } from '@/lib/api';
import styles from './MyPageScreen.module.css';
import type { MyPlanVM } from '@/types/plan';
import { FREE_PLAN_QUOTAS } from '@/types/plan';

// PlanSection (U16, US-SB1) — 현재 플랜 티어(free/plus) · 오늘의 에이전트 쿼터 ·
// (plus면) 만료일. GET /plans/me 소비 전용: 결제/업그레이드 UI 없음(C-12) — 플랜 변경이
// 운영자 부여로만 이뤄진다는 안내 문구가 전부다. 로드 실패는 free 기본값 표시로 조용히
// 강등한다(BR-SB5의 FE 미러, fail-soft): 이 섹션이 실패해도 나머지 설정은 그대로 동작한다.

const FREE_FALLBACK: MyPlanVM = { tier: 'free', quotas: FREE_PLAN_QUOTAS };

export function PlanSection() {
  const [plan, setPlan] = useState<MyPlanVM | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getApiClient().getMyPlan();
        if (!cancelled) setPlan(result);
      } catch {
        // BR-SB5 미러 — 플랜 조회 실패는 free 기본값으로 조용히 강등(오류 배너·재시도 없음).
        if (!cancelled) setPlan(FREE_FALLBACK);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!plan) {
    return (
      <section className={styles.card} data-testid="plan-section-loading">
        <h2 className={styles.cardTitle}>플랜</h2>
        <p className={styles.muted} role="status">
          플랜 정보를 불러오는 중…
        </p>
      </section>
    );
  }

  const isPlus = plan.tier === 'plus';
  return (
    <section className={styles.card} data-testid="plan-section">
      <h2 className={styles.cardTitle}>플랜</h2>
      <p className={styles.tierRow}>
        <span
          className={isPlus ? `${styles.tierBadge} ${styles.tierBadgePlus}` : styles.tierBadge}
          data-testid="plan-tier-badge"
        >
          {isPlus ? 'Plus' : 'Free'}
        </span>
        {isPlus && plan.expiresAt ? (
          <span className={styles.muted} data-testid="plan-expires">
            {formatDate(plan.expiresAt)}까지
          </span>
        ) : null}
      </p>
      <p className={styles.muted}>오늘의 에이전트 쿼터</p>
      <ul className={styles.plainList}>
        <li className={styles.toggleRow}>
          <span>Evidence 에이전트</span>
          <span data-testid="plan-quota-evidence">하루 {plan.quotas.evidenceDaily}회</span>
        </li>
        <li className={styles.toggleRow}>
          <span>Novelty 에이전트</span>
          <span data-testid="plan-quota-novelty">하루 {plan.quotas.noveltyDaily}회</span>
        </li>
      </ul>
      <p className={styles.muted}>플랜 변경(Plus 부여·연장)은 운영자가 관리합니다.</p>
    </section>
  );
}

/** ISO datetime → 날짜 부분만 (로케일 무관 YYYY-MM-DD — 렌더·테스트 결정성). */
function formatDate(iso: string): string {
  return iso.slice(0, 10);
}
