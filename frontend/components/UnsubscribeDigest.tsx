'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import styles from './AuthForm.module.css';
import { getApiClient } from '@/lib/api';

// UnsubscribeDigest (U15, US-TN2/BR-TN4) — landing surface for the digest email's one-click
// opt-out link. Reads ?token=, POSTs once on explicit confirm (RFC 8058-style POST, so a
// mail scanner prefetching the GET can't unsubscribe anyone), and shows a terminal state.
// NO login and NO RouteGuard: the signed token is the only credential — the page never
// blocks or redirects a logged-out user (VerifyEmail precedent).

type State = 'confirm' | 'submitting' | 'done' | 'error';

export function UnsubscribeDigest() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [state, setState] = useState<State>(token ? 'confirm' : 'error');

  const onConfirm = () => {
    if (state !== 'confirm') return;
    setState('submitting');
    void (async () => {
      try {
        await getApiClient().unsubscribeDigest(token);
        setState('done');
      } catch {
        // 무효/만료 토큰(400)과 그 외 실패 모두 동일한 안내로 수렴 — 내부 사유 비노출.
        setState('error');
      }
    })();
  };

  if (state === 'done') {
    return (
      <div className={styles.form} data-testid="unsubscribe-success">
        <p className={styles.formNotice} role="status">
          수신이 해지되었습니다. 더 이상 다이제스트 이메일이 발송되지 않아요.
        </p>
        <Link className={styles.linkButton} href="/">
          홈으로 이동
        </Link>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className={styles.form} data-testid="unsubscribe-error">
        <p className={styles.formError} role="alert">
          링크가 유효하지 않습니다.
        </p>
        <p className={styles.formNotice}>
          이미 처리되었거나 만료된 링크일 수 있어요. 로그인 후 설정에서도 수신을 끌 수 있습니다.
        </p>
        <Link className={styles.linkButton} href="/mypage/settings">
          설정에서 관리하기
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.form} data-testid="unsubscribe-confirm">
      <p className={styles.formNotice} role="status">
        다이제스트 수신을 해지할까요?
      </p>
      <p className={styles.formNotice}>
        해지하면 팔로우 주제의 새 논문 이메일이 더 이상 발송되지 않아요. 설정에서 언제든 다시 켤 수
        있습니다.
      </p>
      <button
        type="button"
        className={styles.submit}
        onClick={onConfirm}
        disabled={state === 'submitting'}
        data-testid="unsubscribe-submit"
      >
        {state === 'submitting' ? '해지하는 중…' : '수신 해지'}
      </button>
    </div>
  );
}
