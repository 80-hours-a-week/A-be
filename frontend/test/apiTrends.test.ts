import { describe, it, expect } from 'vitest';
import { ApiClient } from '@/lib/api/apiClient';
import { UserFacingError } from '@/lib/api/errors';
import type { Transport, TransportRequest, TransportResponse } from '@/lib/api/transport';

// ApiClient U15 (trends) methods — exercised against an injected recorder transport so
// paths, methods, DTO passthrough, and the 409/400 → Korean-message mapping are asserted
// deterministically (apiMypage.test.ts precedent).

const fast = { timeoutMs: 1000, retryBackoffMs: 1 };

function recorder(
  impl: (req: TransportRequest) => TransportResponse,
): { transport: Transport; calls: TransportRequest[] } {
  const calls: TransportRequest[] = [];
  return {
    calls,
    transport: {
      async send(req) {
        calls.push(req);
        return impl(req);
      },
    },
  };
}

describe('ApiClient trends (U15) methods', () => {
  it('lists followed topics (GET /trends/follows)', async () => {
    const body = { topics: [{ id: 't1', topic: 'nerf', createdAt: 'x' }], maxTopics: 10 };
    const r = recorder(() => ({ status: 200, body }));
    const out = await new ApiClient(r.transport, fast).listFollowedTopics();
    expect(out).toEqual(body);
    expect(r.calls[0]).toMatchObject({ method: 'GET', path: '/trends/follows', idempotent: true });
  });

  it('follows a topic (POST /trends/follows, 201)', async () => {
    const body = { id: 't2', topic: 'state space models', createdAt: 'x' };
    const r = recorder(() => ({ status: 201, body }));
    const out = await new ApiClient(r.transport, fast).followTopic('state space models');
    expect(out).toEqual(body);
    expect(r.calls[0]).toMatchObject({
      method: 'POST',
      path: '/trends/follows',
      body: { topic: 'state space models' },
      idempotent: false,
    });
  });

  it('maps the follow-cap 409 to the Korean limit message', async () => {
    const r = recorder(() => ({
      status: 409,
      body: { detail: 'follow limit reached (max 10)' },
    }));
    await expect(new ApiClient(r.transport, fast).followTopic('too many')).rejects.toThrow(
      '팔로우 주제는 최대 10개까지 등록할 수 있어요.',
    );
  });

  it('maps the duplicate-topic 409 to the Korean duplicate message', async () => {
    const r = recorder(() => ({ status: 409, body: { detail: 'topic already followed' } }));
    await expect(new ApiClient(r.transport, fast).followTopic('nerf')).rejects.toThrow(
      '이미 팔로우한 주제예요.',
    );
  });

  it('normalizes a 422 DTO-bounds rejection into a UserFacingError', async () => {
    const r = recorder(() => ({ status: 422, body: { detail: [{ msg: 'too long' }] } }));
    await expect(
      new ApiClient(r.transport, fast).followTopic('x'.repeat(200)),
    ).rejects.toBeInstanceOf(UserFacingError);
  });

  it('unfollows a topic and returns the updated list (DELETE /trends/follows/{id})', async () => {
    const body = { topics: [], maxTopics: 10 };
    const r = recorder(() => ({ status: 200, body }));
    const out = await new ApiClient(r.transport, fast).unfollowTopic('t 1');
    expect(out).toEqual(body);
    expect(r.calls[0]).toMatchObject({
      method: 'DELETE',
      path: '/trends/follows/t%201',
      idempotent: false,
    });
  });

  it('gets and updates digest settings (GET/PUT /trends/settings)', async () => {
    const body = { optedIn: true, cadence: 'weekly', lastSentAt: null };
    const r = recorder(() => ({ status: 200, body }));
    const api = new ApiClient(r.transport, fast);
    expect(await api.getDigestSettings()).toEqual(body);
    expect(await api.updateDigestSettings(true, 'weekly')).toEqual(body);
    expect(r.calls[0]).toMatchObject({ method: 'GET', path: '/trends/settings', idempotent: true });
    expect(r.calls[1]).toMatchObject({
      method: 'PUT',
      path: '/trends/settings',
      body: { optedIn: true, cadence: 'weekly' },
      idempotent: false,
    });
  });

  it('unsubscribes with a token (POST /trends/unsubscribe) and maps 400 to the link message', async () => {
    const ok = recorder(() => ({ status: 200, body: { optedIn: false } }));
    const out = await new ApiClient(ok.transport, fast).unsubscribeDigest('signed-token');
    expect(out).toEqual({ optedIn: false });
    expect(ok.calls[0]).toMatchObject({
      method: 'POST',
      path: '/trends/unsubscribe',
      body: { token: 'signed-token' },
      idempotent: false,
    });

    const bad = recorder(() => ({ status: 400, body: { detail: 'invalid unsubscribe token' } }));
    await expect(new ApiClient(bad.transport, fast).unsubscribeDigest('garbled')).rejects.toThrow(
      '링크가 유효하지 않습니다.',
    );
  });
});
