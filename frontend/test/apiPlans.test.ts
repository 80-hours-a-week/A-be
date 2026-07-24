import { describe, it, expect } from 'vitest';
import { ApiClient } from '@/lib/api/apiClient';
import { UserFacingError } from '@/lib/api/errors';
import type { Transport, TransportRequest, TransportResponse } from '@/lib/api/transport';

// ApiClient U16 (plans) method — recorder-transport contract test (apiTrends.test.ts
// precedent): path/method/idempotency + camelCase body passthrough for GET /plans/me,
// and failure normalization (callers degrade to the free defaults, BR-SB5).

const fast = { timeoutMs: 1000, retryBackoffMs: 1 };

function recorder(impl: (req: TransportRequest) => TransportResponse): {
  transport: Transport;
  calls: TransportRequest[];
} {
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

describe('ApiClient plans (U16) method', () => {
  it('gets the current plan (GET /plans/me) — plus body with expiresAt passes through', async () => {
    const body = {
      tier: 'plus',
      quotas: { evidenceDaily: 90, noveltyDaily: 15 },
      expiresAt: '2026-08-15T00:00:00Z',
    };
    const r = recorder(() => ({ status: 200, body }));
    const out = await new ApiClient(r.transport, fast).getMyPlan();
    expect(out).toEqual(body);
    expect(r.calls[0]).toMatchObject({ method: 'GET', path: '/plans/me', idempotent: true });
  });

  it('passes a free body through without expiresAt', async () => {
    const body = { tier: 'free', quotas: { evidenceDaily: 30, noveltyDaily: 5 } };
    const r = recorder(() => ({ status: 200, body }));
    expect(await new ApiClient(r.transport, fast).getMyPlan()).toEqual(body);
  });

  it('normalizes a failure into a UserFacingError (callers fall back to free, BR-SB5)', async () => {
    const r = recorder(() => ({ status: 500, body: null }));
    await expect(new ApiClient(r.transport, fast).getMyPlan()).rejects.toBeInstanceOf(
      UserFacingError,
    );
  });
});
