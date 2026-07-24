"""U16 Plans — HTTP controller + DI seams (U6 gateway mount, mirrors U15 trends).

The controller obtains the authenticated ``Principal`` from ``request.state`` (set by the U6
gateway middleware) and fails closed to 401 on every route. Grant/revoke are ADMIN-only
(BR-SB4) via the ops-controller precedent: ``AuthorizationGuard.authorize_admin`` including
the MFA requirement (BR-A7), with the same generalized ``403 forbidden`` that reveals
nothing (SEC-9). No payment/billing endpoint exists (C-12).
"""

from __future__ import annotations

import logging

from docsuri_shared.authz import AuthorizationGuard, Decision, Principal
from fastapi import APIRouter, Depends, HTTPException, Request

from .models import (
    GrantRequest,
    GrantResponse,
    PlanAssignment,
    PlanMeResponse,
    PlanQuotas,
)
from .repository import PlanRepository
from .service import PlansService

log = logging.getLogger("docsuri.backend.plans")

router = APIRouter(prefix="/plans", tags=["Plans"])


def get_repo() -> PlanRepository:
    raise RuntimeError("plans repository is not wired")


def get_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


PRINCIPAL_DEP = Depends(get_principal)


def enforce_admin(principal: Principal = PRINCIPAL_DEP) -> Principal:
    """BR-SB4 — mirror of ops.controller.enforce_admin_mfa: role ADMIN + MFA (BR-A7), any
    denial is the same generalized 403 (SEC-9 — no hint whether the target user exists)."""
    decision = AuthorizationGuard.authorize_admin(principal, mfa_verified=principal.mfa_verified)
    if decision != Decision.ALLOW:
        raise HTTPException(status_code=403, detail="forbidden")
    return principal


ADMIN_DEP = Depends(enforce_admin)
REPO_DEP = Depends(get_repo)


def _grant_response(assignment: PlanAssignment) -> GrantResponse:
    return GrantResponse(
        userId=assignment.userId,
        tier=assignment.tier.value,
        startsAt=assignment.startsAt,
        expiresAt=assignment.expiresAt,
        revokedAt=assignment.revokedAt,
    )


@router.get("/me", response_model=PlanMeResponse)
async def get_my_plan(
    principal: Principal = PRINCIPAL_DEP,
    repo: PlanRepository = REPO_DEP,
) -> PlanMeResponse:
    """US-SB1 — own tier + today's quotas (+ expiry when plus). Owner-scoped by construction
    (SEC-8: the principal IS the subject). resolve_quotas is total (BR-SB5), so a plan-store
    failure yields the free view rather than an error."""
    resolution = PlansService(repo).resolve_quotas(principal.user_id)
    return PlanMeResponse(
        tier=resolution.tier,
        quotas=PlanQuotas(
            evidenceDaily=resolution.evidence_daily,
            noveltyDaily=resolution.novelty_daily,
        ),
        expiresAt=resolution.expires_at,
    )


@router.post("/grants", response_model=GrantResponse, status_code=201)
async def grant_plan(
    dto: GrantRequest,
    admin: Principal = ADMIN_DEP,
    repo: PlanRepository = REPO_DEP,
) -> GrantResponse:
    """US-SB2 — ADMIN grants plus for one calendar month, effective immediately (the quota
    shim resolves per request, so the next agent call already sees the plus limits)."""
    try:
        assignment = PlansService(repo).grant(admin.user_id, dto.userId)
    except Exception:  # noqa: BLE001 — SEC-9: generic message, detail stays in the logs
        log.exception("plans: grant failed")
        raise HTTPException(status_code=500, detail="failed to grant plan") from None
    return _grant_response(assignment)


@router.delete("/grants/{user_id}", response_model=GrantResponse)
async def revoke_plan(
    user_id: str,
    admin: Principal = ADMIN_DEP,
    repo: PlanRepository = REPO_DEP,
) -> GrantResponse:
    """US-SB3 — ADMIN revoke marks ``revokedAt`` only: plus keeps running until
    ``expiresAt`` (paid-through-period, BR-SB2). No active grant → a plain 404 that does not
    distinguish "unknown user" from "not on plus" (SEC-9)."""
    try:
        revoked = PlansService(repo).revoke(admin.user_id, user_id)
    except Exception:  # noqa: BLE001 — SEC-9: generic message, detail stays in the logs
        log.exception("plans: revoke failed")
        raise HTTPException(status_code=500, detail="failed to revoke plan") from None
    if revoked is None:
        raise HTTPException(status_code=404, detail="no active plan grant")
    return _grant_response(revoked)


routers = (router,)
