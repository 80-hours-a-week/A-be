"""U11 웹레퍼런스 확장(FR-49) — web-references-extension.md §8 Testable Properties.

BR-WR2(LLM 무접촉)·BR-WR3(≤180자 질의)·BR-WR4(무날조 드랍/dedupe)·BR-WR5(Noop 저하)와
DOCSURI_WEB_REFS_ENABLED=false Noop 배선을 검증한다.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlparse

from docsuri_shared._generated.dtos.evidence_schema import (
    EvidenceItem,
    EvidenceRequest,
    SourceRef,
)

from backend.modules.evidence.assembler import EvidenceComparisonAssembler
from backend.modules.evidence.models import (
    AgentRunContext,
    EvidenceSession,
    EvidenceTurn,
    PaperSearchResult,
    TurnSuccessResult,
)
from backend.modules.evidence.orchestrator import EvidenceAgentOrchestrator
from backend.modules.evidence.web_search import (
    NoopScholarlyWebSearchClient,
    ScholarlyApiSearchClient,
    WebReference,
)

_WEB_MARKER_TITLE = 'WEB-MARKER-TITLE-9f1c'


def _web_ref(title: str = _WEB_MARKER_TITLE, url: str | None = None) -> WebReference:
    return WebReference(
        title=title,
        url=url or 'https://www.semanticscholar.org/paper/abc123',
        doi='10.1000/marker',
        authors=('Ada Lovelace',),
        year=2026,
        source='semantic_scholar',
    )


class _StubSearchTool:
    def search(self, *, topic, scope, paper_ids):
        return PaperSearchResult(
            records=(SimpleNamespace(arxivId='p1'),), query_used=topic, scope='auto'
        )


class _StubDocModelTool:
    def get_doc_model(self, paper_id, version=1):
        return SimpleNamespace()


class _OneClaimExtractor:
    def __init__(self) -> None:
        self.captured_inputs: list[str] = []
        self.calls: list[str] = []

    def extract(self, *, topic, doc_models):
        self.calls.append('extract')
        # BR-WR2 검증용 — 추출기가 받은 입력 전체를 문자열로 캡처한다.
        self.captured_inputs.append(repr((topic, doc_models)))
        return [
            EvidenceItem(
                statement='claim one',
                supporting=[SourceRef(paperId='p1', recordRef='r1')],
                conflicting=[],
            )
        ]


def _run_orchestrator(web_search, extractor=None):
    extractor = extractor or _OneClaimExtractor()
    orchestrator = EvidenceAgentOrchestrator(
        search_tool=_StubSearchTool(),
        doc_model_tool=_StubDocModelTool(),
        extractor=extractor,
        assembler=EvidenceComparisonAssembler(),
        web_search=web_search,
    )
    request = EvidenceRequest(topic='retrieval augmented generation', scope='auto', paperIds=[])
    session = EvidenceSession(owner_id='owner-1')
    turn = EvidenceTurn(session_id=session.session_id, request=request)
    ctx = AgentRunContext(
        session=session,
        current_turn=turn,
        owner_id='owner-1',
        request_id='req-1',
        budget_signal={'state': 'ok'},
    )
    return orchestrator.run(ctx, request)


# ---------------------------------------------------------------------------
# US-WR1 저하 — 프로바이더 장애 주입 → 턴 성공 + webReferences 없음 (BR-WR5)
# ---------------------------------------------------------------------------

def test_turn_succeeds_without_web_references_when_provider_fails() -> None:
    class _FailingWebSearch:
        def search(self, query: str):
            raise RuntimeError('provider outage')

    result = _run_orchestrator(_FailingWebSearch())

    assert isinstance(result, TurnSuccessResult)
    assert result.outcome.state == 'ok'
    assert result.outcome.webReferences is None


def test_empty_web_results_omit_field_and_keep_turn_unchanged() -> None:
    result = _run_orchestrator(NoopScholarlyWebSearchClient())

    assert isinstance(result, TurnSuccessResult)
    assert result.outcome.webReferences is None
    assert [claim.statement for claim in result.outcome.claims] == ['claim one']


# ---------------------------------------------------------------------------
# BR-WR2 구조 검증 — 웹 결과 문자열은 LLM 추출 입력에 절대 미포함
# ---------------------------------------------------------------------------

def test_web_results_never_reach_extractor_input() -> None:
    extractor = _OneClaimExtractor()
    calls = extractor.calls

    class _SpyWebSearch:
        def search(self, query: str):
            calls.append('web_search')
            return (_web_ref(),)

    result = _run_orchestrator(_SpyWebSearch(), extractor=extractor)

    assert isinstance(result, TurnSuccessResult)
    # 웹 결과가 실제로 동봉됐고 —
    assert [ref.title for ref in result.outcome.webReferences] == [_WEB_MARKER_TITLE]
    # 추출 입력에는 웹 결과 문자열이 없다(BR-WR2 — post-hoc 장식).
    assert all(_WEB_MARKER_TITLE not in captured for captured in extractor.captured_inputs)
    # 호출 순서가 구조적 보증이다: 추출 완료 후에만 웹 검색.
    assert calls == ['extract', 'web_search']


# ---------------------------------------------------------------------------
# BR-WR3 — 장문 topic → 전송 질의 ≤180자
# ---------------------------------------------------------------------------

class _RecordingHttp:
    """프로바이더별 최소 성공 응답 + 요청 캡처."""

    def __init__(self, payloads: dict[str, dict] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._payloads = payloads or {}

    def get(self, url: str, *, params: dict):
        self.calls.append((url, params))
        host = urlparse(url).hostname
        payload = self._payloads.get(host, {'data': [], 'results': []})
        return SimpleNamespace(
            status_code=200, json=lambda payload=payload: payload, raise_for_status=lambda: None
        )


def test_long_topic_sends_query_capped_at_180_chars() -> None:
    http = _RecordingHttp()
    client = ScholarlyApiSearchClient(http, max_refs=5)

    client.search('long topic word ' * 100)

    assert len(http.calls) == 2
    for _url, params in http.calls:
        outgoing = params.get('query') or params.get('search')
        assert outgoing is not None
        assert len(outgoing) <= 180


# ---------------------------------------------------------------------------
# BR-WR4 — http URL·URL 결측 드랍, DOI 중복 dedupe, URL dedupe, 상한
# ---------------------------------------------------------------------------

def _s2_paper(title: str, url: str, doi: str | None = None) -> dict:
    return {
        'title': title,
        'url': url,
        'year': 2025,
        'authors': [{'name': 'Author One'}],
        'externalIds': {'DOI': doi} if doi else {},
    }


def _openalex_work(title: str, work_id: str, doi: str | None = None) -> dict:
    return {
        'title': title,
        'id': work_id,
        'doi': doi,
        'publication_year': 2024,
        'authorships': [{'author': {'display_name': 'Author Two'}}],
    }


def test_client_drops_unsafe_items_and_dedupes_by_doi_then_url() -> None:
    http = _RecordingHttp(
        {
            'api.semanticscholar.org': {
                'data': [
                    _s2_paper('Good', 'https://www.semanticscholar.org/paper/a', '10.1/x'),
                    _s2_paper('Insecure', 'http://www.semanticscholar.org/paper/b', '10.2/y'),
                    _s2_paper('NoUrl', ''),
                    _s2_paper('OffHost', 'https://evil.example/paper/z', '10.3/z'),
                ]
            },
            'api.openalex.org': {
                'results': [
                    # 같은 DOI(프로바이더 표기만 다름) — DOI dedupe로 1회만 남는다.
                    _openalex_work(
                        'Good duplicate', 'https://openalex.org/W1', 'https://doi.org/10.1/x'
                    ),
                    _openalex_work('Distinct', 'https://openalex.org/W2', '10.4/w'),
                ]
            },
        }
    )
    client = ScholarlyApiSearchClient(http, max_refs=5)

    refs = client.search('rag evaluation')

    assert [ref.title for ref in refs] == ['Good', 'Distinct']
    assert {ref.source for ref in refs} == {'semantic_scholar', 'openalex'}
    # DOI는 정규화되어 표기 차이와 무관하게 dedupe된다.
    assert refs[0].doi == '10.1/x'


def test_client_dedupes_by_url_and_respects_cap() -> None:
    http = _RecordingHttp(
        {
            'api.semanticscholar.org': {
                'data': [
                    _s2_paper('A', 'https://www.semanticscholar.org/paper/a'),
                    _s2_paper('A again', 'https://www.semanticscholar.org/paper/a'),
                    _s2_paper('B', 'https://www.semanticscholar.org/paper/b'),
                ]
            },
            'api.openalex.org': {
                'results': [
                    _openalex_work('C', 'https://openalex.org/W3'),
                    _openalex_work('D', 'https://openalex.org/W4'),
                ]
            },
        }
    )
    client = ScholarlyApiSearchClient(http, max_refs=3)

    refs = client.search('rag evaluation')

    # URL dedupe('A again' 드랍) 후 상한 3 — 'D'는 cap에 걸려 제외된다.
    assert [ref.title for ref in refs] == ['A', 'B', 'C']


def test_one_provider_failure_uses_other_providers_results(monkeypatch) -> None:
    monkeypatch.setattr('time.sleep', lambda seconds: None)  # 재시도 백오프 대기 생략

    class _HalfBrokenHttp(_RecordingHttp):
        def get(self, url: str, *, params: dict):
            if urlparse(url).hostname == 'api.semanticscholar.org':
                self.calls.append((url, params))
                raise RuntimeError('S2 down')
            return super().get(url, params=params)

    http = _HalfBrokenHttp(
        {'api.openalex.org': {'results': [_openalex_work('C', 'https://openalex.org/W3')]}}
    )
    client = ScholarlyApiSearchClient(http, max_refs=5)

    refs = client.search('rag evaluation')

    assert [ref.title for ref in refs] == ['C']
    # 실패 프로바이더는 1회 재시도(백오프) 후 포기한다.
    s2_calls = [url for url, _ in http.calls if urlparse(url).hostname == 'api.semanticscholar.org']
    assert len(s2_calls) == 2


# ---------------------------------------------------------------------------
# DOCSURI_WEB_REFS_ENABLED=false → Noop 배선, 결과에 필드 부재
# ---------------------------------------------------------------------------

def test_disabled_env_wires_noop_and_field_absent(monkeypatch) -> None:
    from backend.modules.evidence.real_wiring import build_scholarly_web_search
    from backend.modules.evidence.settings import EvidenceSettings

    monkeypatch.setenv('DOCSURI_WEB_REFS_ENABLED', 'false')
    web_search = build_scholarly_web_search(EvidenceSettings.from_env())

    assert isinstance(web_search, NoopScholarlyWebSearchClient)

    result = _run_orchestrator(web_search)
    assert isinstance(result, TurnSuccessResult)
    assert result.outcome.webReferences is None


def test_enabled_by_default_wires_scholarly_client(monkeypatch) -> None:
    from backend.modules.evidence.real_wiring import build_scholarly_web_search
    from backend.modules.evidence.settings import EvidenceSettings

    monkeypatch.delenv('DOCSURI_WEB_REFS_ENABLED', raising=False)
    web_search = build_scholarly_web_search(EvidenceSettings.from_env())

    assert isinstance(web_search, ScholarlyApiSearchClient)


# ---------------------------------------------------------------------------
# §2 승격 — novelty.security 재수출은 동일성 보존(#167 authz 전례)
# ---------------------------------------------------------------------------

def test_hoisted_query_helpers_keep_identity_through_novelty_reexport() -> None:
    from docsuri_shared import external_query

    from backend.modules.novelty import security

    assert security.sanitize_external_query is external_query.sanitize_external_query
    assert security.is_safe_external_url is external_query.is_safe_external_url
    assert security.ALLOWED_EXTERNAL_HOSTS is external_query.ALLOWED_EXTERNAL_HOSTS
