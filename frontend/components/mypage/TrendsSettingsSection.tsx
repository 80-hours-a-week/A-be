'use client';

import { useCallback, useEffect, useState } from 'react';
import { getApiClient, UserFacingError } from '@/lib/api';
import styles from './MyPageScreen.module.css';
import type { DigestCadence, DigestSettingsVM, FollowListVM } from '@/types/trends';
import { MAX_TOPIC_LENGTH } from '@/types/trends';

// TrendsSettingsSection (U15, US-TN1/TN2) — 팔로우 주제 관리 + 이메일 다이제스트 옵트인.
// 설정 화면(MyPageSettingsScreen) 안의 독립 섹션: 로드 실패는 이 섹션의 인라인 오류로만
// 격리되고(fail-soft) 나머지 설정은 그대로 동작한다. 팔로우 목록은 U14/U9 관심 신호와
// 상호 무기록(BR-TN5) — 이 컴포넌트는 개인화 상태를 읽지도 쓰지도 않는다.
// 클라이언트 검증(길이/개수)은 백엔드 DTO 경계를 미러링한 UX 보조일 뿐, 409/422가 최종.

type BusyKey = 'follow' | 'digest' | `unfollow-${string}` | null;

export function TrendsSettingsSection() {
  const [follows, setFollows] = useState<FollowListVM | null>(null);
  const [settings, setSettings] = useState<DigestSettingsVM | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [busy, setBusy] = useState<BusyKey>(null);
  const [topicInput, setTopicInput] = useState('');
  const [followError, setFollowError] = useState<string | null>(null);
  const [digestError, setDigestError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const api = getApiClient();
      const [followList, digestSettings] = await Promise.all([
        api.listFollowedTopics(),
        api.getDigestSettings(),
      ]);
      setFollows(followList);
      setSettings(digestSettings);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onAddTopic = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || !follows) return;
    setFollowError(null);
    // 백엔드 FollowTopicRequest와 동일한 정규화(공백 축약) + 경계 미러(422/409 선제 안내).
    const cleaned = topicInput.trim().split(/\s+/).join(' ');
    if (!cleaned) {
      setFollowError('팔로우할 주제를 입력해 주세요.');
      return;
    }
    if (cleaned.length > MAX_TOPIC_LENGTH) {
      setFollowError(`주제는 ${MAX_TOPIC_LENGTH}자 이하로 입력해 주세요.`);
      return;
    }
    if (follows.topics.length >= follows.maxTopics) {
      setFollowError(`팔로우 주제는 최대 ${follows.maxTopics}개까지 등록할 수 있어요.`);
      return;
    }
    setBusy('follow');
    void (async () => {
      try {
        const created = await getApiClient().followTopic(cleaned);
        setFollows((prev) =>
          prev ? { ...prev, topics: [...prev.topics, created] } : prev,
        );
        setTopicInput('');
      } catch (err) {
        setFollowError(
          err instanceof UserFacingError
            ? err.message
            : '주제를 등록하지 못했습니다. 다시 시도해 주세요.',
        );
      } finally {
        setBusy(null);
      }
    })();
  };

  const onRemoveTopic = (topicId: string) => {
    if (busy) return;
    setFollowError(null);
    setBusy(`unfollow-${topicId}`);
    void (async () => {
      try {
        setFollows(await getApiClient().unfollowTopic(topicId));
      } catch (err) {
        setFollowError(
          err instanceof UserFacingError
            ? err.message
            : '주제를 삭제하지 못했습니다. 다시 시도해 주세요.',
        );
      } finally {
        setBusy(null);
      }
    })();
  };

  const updateDigest = (optedIn: boolean, cadence: DigestCadence) => {
    if (busy) return;
    setDigestError(null);
    setBusy('digest');
    void (async () => {
      try {
        setSettings(await getApiClient().updateDigestSettings(optedIn, cadence));
      } catch (err) {
        // 실패 시 상태를 바꾸지 않으므로 토글/셀렉트는 서버 상태로 자연 복원된다.
        setDigestError(
          err instanceof UserFacingError
            ? err.message
            : '설정을 저장하지 못했습니다. 다시 시도해 주세요.',
        );
      } finally {
        setBusy(null);
      }
    })();
  };

  if (status === 'loading') {
    return (
      <section className={styles.card} data-testid="trends-settings-loading">
        <h2 className={styles.cardTitle}>팔로우 주제 · 이메일 다이제스트</h2>
        <p className={styles.muted} role="status">
          알림 설정을 불러오는 중…
        </p>
      </section>
    );
  }

  if (status === 'error' || !follows || !settings) {
    return (
      <section className={styles.card} data-testid="trends-settings-error">
        <h2 className={styles.cardTitle}>팔로우 주제 · 이메일 다이제스트</h2>
        <p className={styles.error} role="alert">
          알림 설정을 불러오지 못했습니다.
        </p>
        <button type="button" className={styles.action} onClick={() => void load()}>
          다시 시도
        </button>
      </section>
    );
  }

  return (
    <>
      <section className={styles.card} data-testid="trends-follows">
        <h2 className={styles.cardTitle}>팔로우 주제</h2>
        <p className={styles.muted}>
          새 논문을 받아볼 주제를 직접 골라요. 최대 {follows.maxTopics}개까지 등록할 수 있어요.
        </p>
        <form className={styles.inlineForm} onSubmit={onAddTopic} data-testid="trends-follow-form">
          <input
            className={styles.inlineInput}
            type="text"
            value={topicInput}
            onChange={(e) => setTopicInput(e.target.value)}
            placeholder="예: diffusion models"
            aria-label="팔로우할 주제"
            maxLength={MAX_TOPIC_LENGTH}
            data-testid="trends-follow-input"
          />
          <button
            type="submit"
            className={styles.action}
            disabled={busy === 'follow'}
            data-testid="trends-follow-submit"
          >
            팔로우
          </button>
        </form>
        {followError ? (
          <p className={styles.error} role="alert" data-testid="trends-follow-error">
            {followError}
          </p>
        ) : null}
        {follows.topics.length === 0 ? (
          <p className={styles.muted} data-testid="trends-follow-empty">
            아직 팔로우한 주제가 없어요.
          </p>
        ) : (
          <ul className={styles.plainList} data-testid="trends-follow-list">
            {follows.topics.map((topic) => (
              <li key={topic.id} className={styles.itemRow}>
                <span>{topic.topic}</span>
                <button
                  type="button"
                  className={styles.itemRemove}
                  disabled={busy === `unfollow-${topic.id}`}
                  onClick={() => onRemoveTopic(topic.id)}
                  data-testid={`trends-follow-remove-${topic.id}`}
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.card} data-testid="trends-digest">
        <h2 className={styles.cardTitle}>새 논문 이메일 다이제스트</h2>
        <p className={styles.muted}>
          팔로우한 주제의 신규 논문을 이메일로 모아 보내드려요. 켜기 전에는 발송되지 않아요.
        </p>
        <label className={styles.toggleRow}>
          <span>다이제스트 받아보기</span>
          <input
            type="checkbox"
            checked={settings.optedIn}
            disabled={busy === 'digest'}
            onChange={(e) => updateDigest(e.target.checked, settings.cadence)}
            data-testid="trends-digest-opt-in"
          />
        </label>
        {settings.optedIn ? (
          <label className={styles.toggleRow}>
            <span>발송 주기</span>
            <select
              className={styles.select}
              value={settings.cadence}
              disabled={busy === 'digest'}
              onChange={(e) => updateDigest(true, e.target.value as DigestCadence)}
              data-testid="trends-digest-cadence"
            >
              <option value="daily">매일</option>
              <option value="weekly">매주</option>
            </select>
          </label>
        ) : null}
        {digestError ? (
          <p className={styles.error} role="alert" data-testid="trends-digest-error">
            {digestError}
          </p>
        ) : null}
      </section>
    </>
  );
}
