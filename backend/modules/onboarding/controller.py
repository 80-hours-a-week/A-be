"""U14 Onboarding — HTTP controller + DI seams (U6 gateway mount, mirrors U9/U10).

The controller obtains the authenticated ``Principal`` from ``request.state`` (set by the U6
gateway middleware) and fails closed to 401. The onboarding repo seam raises by contract (the
app-shell wires it, like U9); the U9 event recorder and the ORCID identity lookup are resolved
best-effort at request time so a missing/disabled dependency degrades instead of failing
(NFR-P4/US-OB4) and mount order stays irrelevant.
"""

from __future__ import annotations

import os

from docsuri_shared.authz import Principal
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.modules.accounts.integrations.oidc import ORCID_BASES, fetch_orcid_public_record

from .models import (
    ALLOWED_CATEGORIES,
    InterestSelection,
    InterestsResult,
    OnboardingStatusResponse,
    OrcidSuggestionsResponse,
    SkipResult,
)
from .repository import OnboardingRepository
from .service import OnboardingService, derive_suggestions

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def get_repo() -> OnboardingRepository:
    raise RuntimeError("onboarding repository is not wired")


def get_account_repo():
    """ORCID identity lookup seam (``get_orcid_identity(user_id)`` — the U10 AccountRepository
    shape). Defaults to None (standalone/in-memory: no ORCID linkage) → suggestions degrade;
    the app-shell overrides with the U3-backed SqlAccountRepository (mirrors mypage)."""
    return None


def get_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def _observability(request: Request):
    return getattr(request.app.state, "observability", None)


def _interest_recorder(request: Request):
    """user_id + interest_set DTO → U9 EventRecordResult via the app-shell seam
    (``app.state.personalization_record_event``). None when U9 is off/absent → the submit
    degrades to state-only (NFR-P4). Resolved per request so mount order is irrelevant."""
    recorder = getattr(request.app.state, "personalization_record_event", None)
    return recorder if callable(recorder) else None


PRINCIPAL_DEP = Depends(get_principal)
ACCOUNT_REPO_DEP = Depends(get_account_repo)
REPO_DEP = Depends(get_repo)


@router.get("/status", response_model=OnboardingStatusResponse)
async def onboarding_status(
    principal: Principal = PRINCIPAL_DEP,
    repo: OnboardingRepository = REPO_DEP,
) -> OnboardingStatusResponse:
    """Picker gate (US-OB1/OB2): the FE prompts ONLY on ``pending`` (BR-OB4). The allowed
    category whitelist rides along so the FE needs no extra endpoint."""
    status = OnboardingService(repo).status(principal.user_id)
    return OnboardingStatusResponse(state=status.state, categories=list(ALLOWED_CATEGORIES))


@router.post("/interests", response_model=InterestsResult)
async def submit_interests(
    dto: InterestSelection,
    request: Request,
    principal: Principal = PRINCIPAL_DEP,
    repo: OnboardingRepository = REPO_DEP,
) -> InterestsResult:
    """Validated selection (whitelist/non-empty → 422 via the DTO) → ``interest_set`` event
    (non-blocking, BR-OB2 event-path only) → ``state=completed``."""
    service = OnboardingService(
        repo,
        interest_recorder=_interest_recorder(request),
        observability=_observability(request),
    )
    status, record = service.submit_interests(principal.user_id, dto)
    return InterestsResult(state=status.state, eventRecorded=record.recorded, reason=record.reason)


@router.post("/skip", response_model=SkipResult)
async def skip_onboarding(
    principal: Principal = PRINCIPAL_DEP,
    repo: OnboardingRepository = REPO_DEP,
) -> SkipResult:
    return SkipResult(state=OnboardingService(repo).skip(principal.user_id).state)


@router.get("/orcid-suggestions", response_model=OrcidSuggestionsResponse)
async def orcid_suggestions(
    principal: Principal = PRINCIPAL_DEP,
    account_repo=ACCOUNT_REPO_DEP,
) -> OrcidSuggestionsResponse:
    """Propose (never record — BR-OB3) interests from the user's ORCID works via the #347
    public-record helper. MUST never 5xx: every failure degrades to empty + ``degraded=True``
    (US-OB4 picker-only). A non-ORCID account is empty but NOT degraded — nothing failed.
    Note: ``fetch_orcid_public_record`` swallows HTTP errors into empty works itself, so an
    ORCID outage surfaces as empty suggestions without the flag; only lookup-path errors here
    set ``degraded``."""
    try:
        if account_repo is None:
            return OrcidSuggestionsResponse(suggestions=[], degraded=True)
        identity = account_repo.get_orcid_identity(principal.user_id)
        if identity is None:
            return OrcidSuggestionsResponse(suggestions=[], degraded=False)
        _, pub_base = ORCID_BASES.get(os.getenv("ORCID_OIDC_ENV", "prod"), ORCID_BASES["prod"])
        record = await fetch_orcid_public_record(identity.orcid_id, pub_base=pub_base)
        return OrcidSuggestionsResponse(
            suggestions=derive_suggestions(record.get("works") or []), degraded=False
        )
    except Exception:  # noqa: BLE001 — fail-soft: ORCID derivation never breaks onboarding
        return OrcidSuggestionsResponse(suggestions=[], degraded=True)


routers = (router,)
