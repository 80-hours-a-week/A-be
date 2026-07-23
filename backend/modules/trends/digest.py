"""U15 digest job CLI — ``python -m backend.modules.trends.digest [--now ISO8601]``.

The scheduler is intentionally NOT wired (OQ-5: daily harvest is paused; schedule wiring lands
with the harvest-resume decision). This CLI is the §3 관리 진입점: it builds the real wiring —
SQL repo, the corpus search adapter (OpenSearch kNN + keyword assist, windowed by the U1
``dedup_state.ingested_at`` control plane), the EMAIL_PROVIDER seam, and the accounts email
lookup — and runs ``run_digest(now)`` once, printing the report as JSON.

BR-TN7 is enforced structurally: the service gets a ``RefusingEmbeddingPort`` — any embedding
call during the run raises instead of silently billing Bedrock.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from backend.config import Settings

from .models import DigestRunReport, PaperMatch
from .service import RefusingEmbeddingPort, TrendsConfig, TrendsService

log = logging.getLogger("docsuri.backend.trends.digest")

# kNN returns chunk-level hits (many chunks per paper) and the ingest-window filter prunes
# further, so oversample the per-topic cap to keep enough distinct papers post-collapse.
_KNN_OVERSAMPLE = 4
_KEYWORD_TOP_K = 20


class CorpusTrendSearchAdapter:
    """§2 matching over the shared corpus: topic-embedding kNN (reusing the U2 OpenSearch
    reader) + BM25 keyword assist, windowed to papers with ``dedup_state.ingested_at > since``
    (state=INDEXED). Candidates carry their best kNN score; keyword-assist hits kNN missed
    join at the threshold floor (BM25 scores are not comparable to cosine, so lexical match
    gates membership, not rank)."""

    def __init__(self, *, vector_store, lexical_index, session_factory, threshold: float) -> None:
        self._vector_store = vector_store
        self._lexical_index = lexical_index
        self._session_factory = session_factory
        self._threshold = threshold

    def match_topic(
        self, *, embedding: list[float], keywords: list[str], since: datetime, limit: int
    ) -> list[PaperMatch]:
        best: dict[str, PaperMatch] = {}
        knn_hits = self._vector_store.knn_search(embedding, top_k=limit * _KNN_OVERSAMPLE)
        for record, score in knn_hits:
            current = best.get(record.paperId)
            if current is None or score > current.score:
                best[record.paperId] = PaperMatch(
                    paperId=record.paperId, title=record.title, score=score
                )
        # Keyword assist (§2 보조): an exact lexical hit on the topic text qualifies at the
        # threshold floor even when the kNN pass missed it (BM25 scores are not comparable to
        # cosine, so they gate membership, not rank).
        for record, _bm25 in self._lexical_index.bm25_search(keywords, top_k=_KEYWORD_TOP_K):
            if record.paperId not in best:
                best[record.paperId] = PaperMatch(
                    paperId=record.paperId, title=record.title, score=self._threshold
                )
        windowed = self._filter_ingested_after(list(best.values()), since)
        return sorted(windowed, key=lambda m: (-m.score, m.paperId))[:limit]

    def _filter_ingested_after(
        self, matches: list[PaperMatch], since: datetime
    ) -> list[PaperMatch]:
        if not matches:
            return []
        from sqlalchemy import text

        session = self._session_factory()
        try:
            rows = session.execute(
                text(
                    "SELECT paper_id FROM dedup_state "
                    "WHERE paper_id = ANY(:ids) AND state = 'INDEXED' "
                    "AND ingested_at IS NOT NULL AND ingested_at > :since"
                ),
                {"ids": [m.paperId for m in matches], "since": since},
            ).all()
        finally:
            session.close()
        fresh = {row[0] for row in rows}
        return [m for m in matches if m.paperId in fresh]


class EmailSeamDigestAdapter:
    """Sync facade over the existing async EMAIL_PROVIDER seam (accounts ``_send`` primitive:
    render → generic send, same SES/Resend/Mock selection as every other DocSuri email)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def send(self, to: str, subject: str, text: str, html: str) -> bool:
        return asyncio.run(self._client._send(to, subject, text, html))


class SqlRecipientEmails:
    """user_id → deliverable address from the U3 accounts table (ACTIVE accounts only)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_email(self, user_id: str) -> str | None:
        from sqlalchemy import text

        session = self._session_factory()
        try:
            row = session.execute(
                text("SELECT email FROM accounts WHERE id = :id AND status = 'ACTIVE'"),
                {"id": user_id},
            ).first()
            return row[0] if row else None
        finally:
            session.close()


def _build_search_port(session_factory, config: TrendsConfig):
    """Real corpus adapter when the U2 read path is configured; else the Noop default (no
    candidates → BR-TN2 suppresses every send — safe on a bare checkout)."""
    from discovery.adapters.settings import DiscoverySettings

    ds = DiscoverySettings.from_env()
    if not ds.search_enabled:
        log.warning("trends digest: OpenSearch not configured — matching disabled (no sends)")
        return None
    from discovery.adapters.opensearch_index import (
        OpenSearchClientFactory,
        OpenSearchLexicalIndexAdapter,
        OpenSearchVectorStoreAdapter,
    )

    client = OpenSearchClientFactory.build(
        endpoint=ds.opensearch_endpoint,
        region_name=ds.aws_region,
        username=ds.opensearch_username,
        password=ds.opensearch_password,
        use_ssl=ds.opensearch_use_ssl,
        verify_certs=ds.opensearch_verify_certs,
    )
    return CorpusTrendSearchAdapter(
        vector_store=OpenSearchVectorStoreAdapter(client, ds.opensearch_index),
        lexical_index=OpenSearchLexicalIndexAdapter(client, ds.opensearch_index),
        session_factory=session_factory,
        threshold=config.match_threshold,
    )


def _build_email_port():
    import os

    from backend.modules.accounts.integrations.email import get_email_client

    client = get_email_client(
        env=os.getenv("ENV", "local"),
        sender_email=os.getenv("SES_SENDER_EMAIL", "no-reply@docsuri.org"),
        region=os.getenv("SES_REGION", "ap-northeast-2"),
    )
    return EmailSeamDigestAdapter(client)


def run(now: datetime) -> DigestRunReport:
    settings = Settings.from_env()
    if not settings.database_url.startswith(("postgresql", "postgres")):
        log.error("trends digest: DATABASE_URL is not Postgres — nothing to sweep")
        return DigestRunReport(ranAt=now)

    from backend.db import make_engine, make_session_factory
    from backend.modules.trends.repository import SqlTrendsRepository

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    config = TrendsConfig.from_env()
    session = session_factory()
    try:
        service = TrendsService(
            SqlTrendsRepository(session),
            embedding_port=RefusingEmbeddingPort(),  # BR-TN7: zero embedding calls
            search_port=_build_search_port(session_factory, config),
            email_port=_build_email_port(),
            recipient_emails=SqlRecipientEmails(session_factory),
            config=config,
        )
        report = service.run_digest(now)
        session.commit()
        return report
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run one U15 digest sweep (run_digest(now)).")
    parser.add_argument(
        "--now",
        help="Logical run time (ISO-8601, default: current UTC time). "
        "Re-running with the same value is idempotent (§6 watermark).",
    )
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    report = run(now)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
