"""U15 Trends — HTTP controller + DI seams (U6 gateway mount, mirrors U14/U9).

The controller obtains the authenticated ``Principal`` from ``request.state`` (set by the U6
gateway middleware) and fails closed to 401 on every owner-scoped route. The one exception is
POST /trends/unsubscribe (§4): it is authenticated by the signed owner-scoped token alone (no
login, BR-TN4) and NEVER 5xxes — any invalid/stale/garbled token is a 4xx.

The repo seam raises by contract (the app-shell wires sql/in-memory, like U14); the embedding
port defaults to the deterministic local fake and is overridden by the app-shell with the real
Bedrock query embedder when the corpus read path is configured.
"""

from __future__ import annotations

from docsuri_shared.authz import Principal
from fastapi import APIRouter, Depends, HTTPException, Request

from .models import (
    DigestSettingsResponse,
    DigestSettingsUpdate,
    FollowedTopicResponse,
    FollowListResponse,
    FollowTopicRequest,
    UnsubscribeRequest,
    UnsubscribeResponse,
)
from .repository import TrendsRepository
from .service import (
    DeterministicFakeEmbedding,
    DuplicateTopic,
    InvalidUnsubscribeToken,
    TopicEmbeddingPort,
    TopicLimitExceeded,
    TrendsService,
    UnsubscribeTokenSigner,
    build_token_signer,
)

router = APIRouter(prefix="/trends", tags=["Trends"])

# Module-level defaults (per-process singletons): the fake embedder is stateless and the
# signer must be shared across requests so issued tokens verify (env key or process-ephemeral).
_DEFAULT_EMBEDDING: TopicEmbeddingPort = DeterministicFakeEmbedding()
_DEFAULT_SIGNER: UnsubscribeTokenSigner | None = None


def get_repo() -> TrendsRepository:
    raise RuntimeError("trends repository is not wired")


def get_embedding_port() -> TopicEmbeddingPort:
    """Topic embedding seam — called only at follow registration (BR-TN7). Default is the
    deterministic local fake; the app-shell overrides with the Bedrock query embedder (same
    model/space as the corpus, functional-design §1) when the real read path is configured."""
    return _DEFAULT_EMBEDDING


def get_token_signer() -> UnsubscribeTokenSigner:
    global _DEFAULT_SIGNER
    if _DEFAULT_SIGNER is None:
        _DEFAULT_SIGNER = build_token_signer()
    return _DEFAULT_SIGNER


def get_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def _observability(request: Request):
    return getattr(request.app.state, "observability", None)


PRINCIPAL_DEP = Depends(get_principal)
REPO_DEP = Depends(get_repo)
EMBEDDING_DEP = Depends(get_embedding_port)
SIGNER_DEP = Depends(get_token_signer)


def _topic_response(topic) -> FollowedTopicResponse:
    return FollowedTopicResponse(id=topic.id, topic=topic.topic, createdAt=topic.createdAt)


@router.get("/follows", response_model=FollowListResponse)
async def list_follows(
    principal: Principal = PRINCIPAL_DEP,
    repo: TrendsRepository = REPO_DEP,
) -> FollowListResponse:
    topics = TrendsService(repo).list_follows(principal.user_id)
    return FollowListResponse(topics=[_topic_response(t) for t in topics])


@router.post("/follows", response_model=FollowedTopicResponse, status_code=201)
async def follow_topic(
    dto: FollowTopicRequest,
    request: Request,
    principal: Principal = PRINCIPAL_DEP,
    repo: TrendsRepository = REPO_DEP,
    embedding: TopicEmbeddingPort = EMBEDDING_DEP,
) -> FollowedTopicResponse:
    """Register a topic — embedded ONCE here (US-TN1/BR-TN7). Bounds (non-empty, length) are
    DTO-enforced → 422; the per-user cap and duplicates are state conflicts → 409."""
    service = TrendsService(repo, embedding_port=embedding, observability=_observability(request))
    try:
        topic = service.follow_topic(principal.user_id, dto)
    except DuplicateTopic as exc:
        raise HTTPException(status_code=409, detail="topic already followed") from exc
    except TopicLimitExceeded as exc:
        raise HTTPException(
            status_code=409, detail=f"follow limit reached (max {exc})"
        ) from exc
    return _topic_response(topic)


@router.delete("/follows/{topic_id}", response_model=FollowListResponse)
async def unfollow_topic(
    topic_id: str,
    principal: Principal = PRINCIPAL_DEP,
    repo: TrendsRepository = REPO_DEP,
) -> FollowListResponse:
    """Owner-scoped delete — another user's topic id is indistinguishable from absent (404)."""
    service = TrendsService(repo)
    if not service.unfollow_topic(principal.user_id, topic_id):
        raise HTTPException(status_code=404, detail="followed topic not found")
    topics = service.list_follows(principal.user_id)
    return FollowListResponse(topics=[_topic_response(t) for t in topics])


@router.get("/settings", response_model=DigestSettingsResponse)
async def get_digest_settings(
    principal: Principal = PRINCIPAL_DEP,
    repo: TrendsRepository = REPO_DEP,
) -> DigestSettingsResponse:
    settings = TrendsService(repo).get_settings(principal.user_id)
    return DigestSettingsResponse(
        optedIn=settings.optedIn, cadence=settings.cadence, lastSentAt=settings.lastSentAt
    )


@router.put("/settings", response_model=DigestSettingsResponse)
async def put_digest_settings(
    dto: DigestSettingsUpdate,
    principal: Principal = PRINCIPAL_DEP,
    repo: TrendsRepository = REPO_DEP,
) -> DigestSettingsResponse:
    """US-TN2 — takes effect immediately (BR-TN1/TN4); also rotates the settings version, so
    outstanding unsubscribe tokens are invalidated (SEC-8)."""
    settings = TrendsService(repo).put_settings(principal.user_id, dto.optedIn, dto.cadence)
    return DigestSettingsResponse(
        optedIn=settings.optedIn, cadence=settings.cadence, lastSentAt=settings.lastSentAt
    )


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe(
    dto: UnsubscribeRequest,
    repo: TrendsRepository = REPO_DEP,
    signer: UnsubscribeTokenSigner = SIGNER_DEP,
) -> UnsubscribeResponse:
    """No-login one-click opt-out (BR-TN4, RFC 8058-compatible POST). The signed token is the
    only credential and is valid solely for its owner. NEVER 5xx: every failure — bad
    signature, unknown user, stale version, unexpected error — is a 400."""
    try:
        settings = TrendsService(repo, token_signer=signer).unsubscribe(dto.token)
        return UnsubscribeResponse(optedIn=settings.optedIn)
    except InvalidUnsubscribeToken as exc:
        raise HTTPException(status_code=400, detail="invalid unsubscribe token") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — contract: the unsubscribe path never 5xxes
        raise HTTPException(status_code=400, detail="invalid unsubscribe token") from exc


routers = (router,)
