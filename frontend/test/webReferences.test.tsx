import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EvidenceWebReferences } from '@/components/agent/AgentChatScreen';
import { evidenceWebReferencesFixture } from '@/mocks/agentFixtures';

// U11 확장(FR-49/US-WR1) — 성공 턴 하단 접이식 "웹 레퍼런스" 섹션.
describe('EvidenceWebReferences', () => {
  it('renders the collapsible section with linked items, authors, year and source badges', () => {
    render(<EvidenceWebReferences references={evidenceWebReferencesFixture} />);

    expect(screen.getByTestId('evidence-web-references')).toBeInTheDocument();
    expect(screen.getByText('웹 레퍼런스')).toBeInTheDocument();
    expect(screen.getByText('2건')).toBeInTheDocument();

    // 제목 링크 — href는 프로바이더 반환 URL 원본 그대로(BR-WR4), 새 탭 + noopener.
    const s2Link = screen.getByRole('link', { name: evidenceWebReferencesFixture[0].title });
    expect(s2Link).toHaveAttribute('href', evidenceWebReferencesFixture[0].url);
    expect(s2Link).toHaveAttribute('target', '_blank');
    expect(s2Link).toHaveAttribute('rel', 'noopener noreferrer');

    const openAlexLink = screen.getByRole('link', { name: evidenceWebReferencesFixture[1].title });
    expect(openAlexLink).toHaveAttribute('href', evidenceWebReferencesFixture[1].url);
    expect(openAlexLink).toHaveAttribute('target', '_blank');
    expect(openAlexLink).toHaveAttribute('rel', 'noopener noreferrer');

    // 저자 축약(3명 이상 → 첫 저자 외 N명) · 연도 · 출처 뱃지.
    expect(screen.getByText('Cheng Xu 외 3명')).toBeInTheDocument();
    expect(screen.getByText('Manley Roberts, Himanshu Thakur')).toBeInTheDocument();
    expect(screen.getByText('2024')).toBeInTheDocument();
    expect(screen.getByText('2023')).toBeInTheDocument();
    expect(screen.getByText('Semantic Scholar')).toBeInTheDocument();
    expect(screen.getByText('OpenAlex')).toBeInTheDocument();
  });

  it('renders nothing when webReferences is absent', () => {
    const { container } = render(<EvidenceWebReferences />);
    expect(screen.queryByTestId('evidence-web-references')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when webReferences is an empty array', () => {
    const { container } = render(<EvidenceWebReferences references={[]} />);
    expect(screen.queryByTestId('evidence-web-references')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('does not linkify non-http(s) URLs (BR-WR4 defence in depth)', () => {
    render(
      <EvidenceWebReferences
        references={[
          {
            title: 'Unsafe scheme entry',
            // eslint-disable-next-line no-script-url
            url: 'javascript:alert(1)',
            source: 'openalex',
          },
        ]}
      />,
    );

    expect(screen.getByText('Unsafe scheme entry')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
