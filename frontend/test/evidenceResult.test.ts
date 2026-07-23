import { describe, expect, it } from 'vitest';
import {
  abstainReasonLabel,
  formatWebReferenceAuthors,
  parseAgentContent,
} from '@/lib/agentChat/evidenceResult';

describe('parseAgentContent', () => {
  it('parses a successful EvidenceResult JSON payload', () => {
    const content = JSON.stringify({
      state: 'ok',
      claims: [
        {
          statement: 'Cottention achieves native linear memory complexity.',
          supporting: [
            {
              paperId: '2409.18747v1',
              recordRef: '2409.18747v1',
              anchor: null,
              quote: 'Cottention achieves native linear memory complexity.',
            },
          ],
          conflicting: [],
        },
      ],
      coverage: { paperCount: 3, queryUsed: 'transformer attention' },
    });

    const parsed = parseAgentContent(content);
    expect(parsed.kind).toBe('evidence');
    if (parsed.kind === 'evidence') {
      expect(parsed.result.claims).toHaveLength(1);
      expect(parsed.result.claims[0].supporting[0].paperId).toBe('2409.18747v1');
      expect(parsed.result.coverage.paperCount).toBe(3);
    }
  });

  it('passes through the optional answer narrative field', () => {
    const content = JSON.stringify({
      state: 'ok',
      claims: [],
      coverage: { paperCount: 0 },
      answer: "'self-attention reduces computation' 문장이 포함된 논문을 총 1편 찾았습니다.",
    });

    const parsed = parseAgentContent(content);
    expect(parsed.kind).toBe('evidence');
    if (parsed.kind === 'evidence') {
      expect(parsed.result.answer).toContain('1편');
    }
  });

  it('parses an abstain response and maps it to a human-readable label', () => {
    const parsed = parseAgentContent('[abstain] insufficient_evidence');
    expect(parsed.kind).toBe('abstain');
    if (parsed.kind === 'abstain') {
      expect(parsed.reason).toBe('insufficient_evidence');
      expect(abstainReasonLabel(parsed.reason)).toBe('근거가 충분하지 않아 답변을 보류했습니다.');
    }
  });

  it('falls back to a generic label for an unknown abstain reason', () => {
    expect(abstainReasonLabel('some_new_reason')).toBe('답변을 생성하지 못했습니다.');
  });

  it('parses an error response', () => {
    const parsed = parseAgentContent('[error] evidence_unavailable');
    expect(parsed.kind).toBe('error');
  });

  it('treats plain text (e.g. user messages, novelty mode) as text', () => {
    const parsed = parseAgentContent(
      'transformer 모델의 attention 메커니즘에 대한 최근 연구 동향은?',
    );
    expect(parsed.kind).toBe('text');
    if (parsed.kind === 'text') {
      expect(parsed.text).toContain('transformer');
    }
  });

  it('does not choke on JSON-looking text that is not an EvidenceResult', () => {
    const parsed = parseAgentContent('{"foo": "bar"}');
    expect(parsed.kind).toBe('text');
  });

  // U11 웹 레퍼런스(FR-49) — optional 필드가 파싱을 그대로 통과한다.
  it('passes through the optional webReferences field', () => {
    const webReferences = [
      {
        title: 'Benchmark Data Contamination of Large Language Models: A Survey',
        url: 'https://www.semanticscholar.org/paper/2406.04244',
        doi: '10.48550/arXiv.2406.04244',
        authors: ['Cheng Xu'],
        year: 2024,
        source: 'semantic_scholar',
      },
    ];
    const parsed = parseAgentContent(
      JSON.stringify({ state: 'ok', claims: [], coverage: { paperCount: 0 }, webReferences }),
    );

    expect(parsed.kind).toBe('evidence');
    if (parsed.kind === 'evidence') {
      expect(parsed.result.webReferences).toEqual(webReferences);
    }
  });
});

describe('formatWebReferenceAuthors', () => {
  it('returns null when authors are absent or empty', () => {
    expect(formatWebReferenceAuthors(undefined)).toBeNull();
    expect(formatWebReferenceAuthors([])).toBeNull();
  });

  it('lists up to two authors verbatim', () => {
    expect(formatWebReferenceAuthors(['Cheng Xu'])).toBe('Cheng Xu');
    expect(formatWebReferenceAuthors(['Cheng Xu', 'Shuhao Guan'])).toBe('Cheng Xu, Shuhao Guan');
  });

  it('abbreviates three or more authors as "first author 외 N명"', () => {
    expect(formatWebReferenceAuthors(['Cheng Xu', 'Shuhao Guan', 'Derek Greene'])).toBe(
      'Cheng Xu 외 2명',
    );
  });
});
