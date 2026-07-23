"""Scholarly web-reference search (U11 웹레퍼런스 확장 §1 — FR-49, C-11).

Semantic Scholar Graph + OpenAlex(둘 다 무키)를 질의해 **표시 메타만** 담은
``WebReference``를 돌려준다. 링크백 전용(BR-WR1): 페이지 fetch·본문/초록 저장 없음.
URL/DOI는 프로바이더 반환 원본만 — 조립·생성 금지(BR-WR4 무날조), https·허용 호스트
검증 실패 항목은 드랍. 장애·타임아웃은 조용한 저하(BR-WR5): 한 프로바이더가 죽으면
다른 쪽 결과만, 둘 다 죽으면 빈 튜플. 전체 시간 예산은 주입된 httpx client의
timeout이 bound한다(NFR-P6 — 배선은 real_wiring 참조).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from docsuri_shared.external_query import is_safe_external_url, sanitize_external_query

log = logging.getLogger(__name__)

# 프로바이더 표시 URL이 실릴 수 있는 호스트만(BR-WR4 — novelty ALLOWED_EXTERNAL_HOSTS와
# 별개의 좁은 표면). suffix 매칭이므로 www.semanticscholar.org 등 서브도메인 포함.
SCHOLARLY_ALLOWED_HOSTS = frozenset({'semanticscholar.org', 'openalex.org', 'doi.org'})

_SEMANTIC_SCHOLAR_SEARCH_URL = 'https://api.semanticscholar.org/graph/v1/paper/search'
_OPENALEX_WORKS_URL = 'https://api.openalex.org/works'
_MAX_DISPLAY_AUTHORS = 3  # 표시용 상위 몇 명(§1)
_RETRY_BACKOFF_SECONDS = 0.5  # transient 실패 1회 재시도 간격(§9 S2 무키 레이트리밋 유의)
_DOI_URL_PREFIX = 'https://doi.org/'


@dataclass(frozen=True)
class WebReference:
    """표시 메타만 — 본문/초록 텍스트를 담지 않는다(C-11)."""

    title: str
    url: str
    doi: str | None
    authors: tuple[str, ...]
    year: int | None
    source: str  # 'semantic_scholar' | 'openalex'


class ScholarlyWebSearchPort(Protocol):
    def search(self, query: str) -> tuple[WebReference, ...]: ...


class NoopScholarlyWebSearchClient:
    """기본 배선(테스트·DOCSURI_WEB_REFS_ENABLED=false)이자 저하 경로(§1)."""

    def search(self, query: str) -> tuple[WebReference, ...]:
        return ()


class ScholarlyApiSearchClient:
    """Semantic Scholar Graph /paper/search + OpenAlex /works?search= 병합 클라이언트.

    novelty ``ExternalApiSearchClient``와 동일한 주입 스타일 — httpx client는 배선이
    timeout과 함께 주입한다. 프로바이더별 실패 격리: 한쪽 예외는 다른 쪽 결과에
    무영향(BR-WR5/BR-WR6 전례).
    """

    def __init__(
        self,
        client: Any,
        *,
        max_refs: int = 5,
        mailto: str | None = None,
    ) -> None:
        self._client = client
        self._max_refs = max_refs
        self._mailto = mailto  # OpenAlex polite pool(§9 — DOCSURI_OPENALEX_MAILTO)

    def search(self, query: str) -> tuple[WebReference, ...]:
        cleaned = sanitize_external_query(query)  # BR-WR3 — ≤180자, topic만
        refs: list[WebReference] = []
        for source, fetch in (
            ('semantic_scholar', self._semantic_scholar),
            ('openalex', self._openalex),
        ):
            try:
                refs.extend(fetch(cleaned))
            except Exception:  # noqa: BLE001 — 한 프로바이더 실패는 다른 쪽에 무영향(BR-WR5)
                log.warning('%s web reference search unavailable', source)
        return tuple(_dedupe(refs)[: self._max_refs])

    def _semantic_scholar(self, query: str) -> list[WebReference]:
        payload = self._json(
            _SEMANTIC_SCHOLAR_SEARCH_URL,
            params={
                'query': query,
                'fields': 'title,externalIds,url,year,authors,venue',
                'limit': self._max_refs,
            },
        )
        refs = []
        for paper in (payload.get('data') or [])[: self._max_refs]:
            ref = _reference(
                title=str(paper.get('title') or ''),
                url=str(paper.get('url') or ''),
                doi=(paper.get('externalIds') or {}).get('DOI'),
                authors=[str(a.get('name') or '') for a in paper.get('authors') or []],
                year=paper.get('year'),
                source='semantic_scholar',
            )
            if ref is not None:
                refs.append(ref)
        return refs

    def _openalex(self, query: str) -> list[WebReference]:
        params: dict[str, Any] = {'search': query, 'per-page': self._max_refs}
        if self._mailto:
            params['mailto'] = self._mailto
        payload = self._json(_OPENALEX_WORKS_URL, params=params)
        refs = []
        for work in (payload.get('results') or [])[: self._max_refs]:
            authorships = work.get('authorships') or []
            ref = _reference(
                title=str(work.get('title') or work.get('display_name') or ''),
                # OpenAlex id는 프로바이더가 반환한 work URL(조립 아님 — BR-WR4).
                url=str(work.get('id') or ''),
                doi=work.get('doi'),
                authors=[
                    str((a.get('author') or {}).get('display_name') or '') for a in authorships
                ],
                year=work.get('publication_year'),
                source='openalex',
            )
            if ref is not None:
                refs.append(ref)
        return refs

    def _json(self, url: str, *, params: dict[str, Any]) -> Any:
        """transient 실패 1회 재시도(단순 백오프) 후 포기(§1) — 상위가 저하로 수렴."""
        try:
            return self._get_json(url, params)
        except Exception:  # noqa: BLE001 — 1회 재시도 후 최종 예외는 상위 격리로 전파
            time.sleep(_RETRY_BACKOFF_SECONDS)
            return self._get_json(url, params)

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        response = self._client.get(url, params=params)
        if getattr(response, 'status_code', 200) >= 400:
            raise RuntimeError('scholarly API unavailable')
        raise_for_status = getattr(response, 'raise_for_status', None)
        if raise_for_status is not None:
            raise_for_status()
        return response.json()


def _reference(
    *,
    title: str,
    url: str,
    doi: Any,
    authors: list[str],
    year: Any,
    source: str,
) -> WebReference | None:
    """프로바이더 항목 → WebReference. 제목·URL 결측 또는 https·호스트 검증 실패는 드랍
    (BR-WR4 — 조립로 메꾸지 않는다)."""
    title = title.strip()
    url = url.strip()
    if not title or not url:
        return None
    if not is_safe_external_url(url, SCHOLARLY_ALLOWED_HOSTS):
        return None
    return WebReference(
        title=title,
        url=url,
        doi=_normalize_doi(doi),
        authors=tuple(name for name in (a.strip() for a in authors) if name)[
            :_MAX_DISPLAY_AUTHORS
        ],
        year=int(year) if isinstance(year, int) else None,
        source=source,
    )


def _normalize_doi(doi: Any) -> str | None:
    """dedupe 키 정규화 — OpenAlex는 DOI를 https://doi.org/ URL 형태로 반환한다.
    프로바이더 반환값의 표기 정규화일 뿐 새 식별자 생성이 아니다(BR-WR4)."""
    if not isinstance(doi, str) or not doi.strip():
        return None
    cleaned = doi.strip()
    if cleaned.lower().startswith(_DOI_URL_PREFIX):
        cleaned = cleaned[len(_DOI_URL_PREFIX):]
    return cleaned or None


def _dedupe(refs: list[WebReference]) -> list[WebReference]:
    """DOI 우선, 없으면 URL로 dedupe(§1) — 먼저 온 항목이 이긴다."""
    seen_dois: set[str] = set()
    seen_urls: set[str] = set()
    deduped: list[WebReference] = []
    for ref in refs:
        doi_key = ref.doi.lower() if ref.doi else None
        if doi_key and doi_key in seen_dois:
            continue
        if ref.url in seen_urls:
            continue
        if doi_key:
            seen_dois.add(doi_key)
        seen_urls.add(ref.url)
        deduped.append(ref)
    return deduped
