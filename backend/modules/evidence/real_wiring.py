"""build_evidence_orchestrator — U11 실 어댑터 조립 (real-first, TD-E1~E11).

Discovery(U2) 어댑터 재사용:
  BedrockCohereQueryEmbedder → EvidencePaperSearchTool.EmbeddingPort
  OpenSearchVectorStoreAdapter → VectorStorePort
  OpenSearchLexicalIndexAdapter → LexicalIndexPort
  OpenSearchPaperLookupAdapter → PaperLookupPort

Summarization(U7) 어댑터 재사용:
  S3DocModelReader → EvidenceDocModelTool

신규:
  EvidenceExtractor → Bedrock Sonnet 4.6 (claude-sonnet-4-6)
"""

from __future__ import annotations

from dataclasses import dataclass

from .assembler import EvidenceComparisonAssembler
from .extractor import EvidenceExtractor
from .orchestrator import EvidenceAgentOrchestrator
from .settings import EvidenceSettings
from .tools import EvidenceDocModelTool, EvidencePaperSearchTool
from .web_search import (
    NoopScholarlyWebSearchClient,
    ScholarlyApiSearchClient,
    ScholarlyWebSearchPort,
)


@dataclass(frozen=True)
class EvidenceBundle:
    orchestrator: EvidenceAgentOrchestrator
    settings: EvidenceSettings


def build_evidence_orchestrator(
    settings: EvidenceSettings, cost_guard: object | None = None
) -> EvidenceBundle:
    """실 어댑터 조립 — DOCSURI_DOCMODEL_BUCKET + OpenSearch 설정 필요.

    cost_guard(U6 단일 권위)를 주면 orchestrator 비용 게이트 + extractor 지출 기록에
    연결된다(NFR-C1).
    """
    # --- Discovery 어댑터 (U2 재사용) ---
    from discovery.adapters.bedrock_embedding import BedrockCohereQueryEmbedder
    from discovery.adapters.opensearch_index import (
        OpenSearchClientFactory,
        OpenSearchLexicalIndexAdapter,
        OpenSearchPaperLookupAdapter,
        OpenSearchVectorStoreAdapter,
    )
    from discovery.adapters.settings import DiscoverySettings

    d_settings = DiscoverySettings.from_env()
    os_client = OpenSearchClientFactory.build(
        endpoint=d_settings.opensearch_endpoint,
        region_name=settings.region_name,
        username=d_settings.opensearch_username,
        password=d_settings.opensearch_password,
        use_ssl=d_settings.opensearch_use_ssl,
        verify_certs=d_settings.opensearch_verify_certs,
    )

    embedding = BedrockCohereQueryEmbedder(
        model_id=d_settings.bedrock_model_id,
        # Bedrock region decoupled from region_name (OpenSearch SigV4): Cohere v3 isn't in
        # ap-northeast-2, so query embedding must go cross-region. Mirrors discovery real_wiring.
        region_name=d_settings.bedrock_region or settings.region_name,
    )
    vector_store = OpenSearchVectorStoreAdapter(os_client, d_settings.opensearch_index)
    lexical_index = OpenSearchLexicalIndexAdapter(os_client, d_settings.opensearch_index)
    paper_lookup = OpenSearchPaperLookupAdapter(os_client, d_settings.opensearch_index)

    search_tool = EvidencePaperSearchTool(
        embedding=embedding,
        vector_store=vector_store,
        lexical_index=lexical_index,
        paper_lookup=paper_lookup,
    )

    # --- S3 DocModel 리더 (U7 재사용) ---
    from summarization.adapters.s3_docmodel import S3DocModelReader

    doc_model_reader = S3DocModelReader(
        bucket=settings.docmodel_bucket,
        region_name=settings.region_name,
    )
    doc_model_tool = EvidenceDocModelTool(doc_model_reader=doc_model_reader)

    # --- EvidenceExtractor (Bedrock Sonnet 4.6) ---
    extractor = EvidenceExtractor(
        model_id=settings.model_id,
        region_name=settings.region_name,
        cost_guard=cost_guard,
    )

    # --- Assembler & Orchestrator ---
    assembler = EvidenceComparisonAssembler()
    orchestrator = EvidenceAgentOrchestrator(
        search_tool=search_tool,
        doc_model_tool=doc_model_tool,
        extractor=extractor,
        assembler=assembler,
        cost_guard=cost_guard,
        web_search=build_scholarly_web_search(settings),
    )

    return EvidenceBundle(orchestrator=orchestrator, settings=settings)


def build_scholarly_web_search(settings: EvidenceSettings) -> ScholarlyWebSearchPort:
    """FR-49 웹레퍼런스 배선 — DOCSURI_WEB_REFS_ENABLED=false면 Noop(기본 배선·저하 경로).

    전체 시간 예산(DOCSURI_WEB_REFS_TIMEOUT_S, 기본 4s)은 ``search()``의 monotonic
    deadline이 bound한다(NFR-P6 — 프로바이더 병렬 실행, 미완 포기). httpx client
    timeout은 같은 값으로 요청 1건의 상한만 담당한다 — 프로바이더가 병렬이므로 단일
    스톨 요청도 예산을 넘지 못한다. U12 novelty의 scholarly 합류도 이 팩토리를
    재사용한다(US-WR2).
    """
    if not settings.web_refs_enabled:
        return NoopScholarlyWebSearchClient()

    import httpx

    return ScholarlyApiSearchClient(
        httpx.Client(
            timeout=settings.web_refs_timeout_s,
            headers={'User-Agent': 'DocSuri-Evidence/1.0'},
        ),
        max_refs=settings.web_refs_max,
        timeout_s=settings.web_refs_timeout_s,
        mailto=settings.openalex_mailto,
    )
