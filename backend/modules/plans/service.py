"""U16 Plans — service layer: grant/revoke, quota resolution, and the spend rollup.

The service is deliberately a VALUE SUPPLIER only (BR-SB3/NFR-C1): it never touches the
limiter, Redis keys, windows, or CostGuard. ``resolve_quotas`` is the single derivation of
plan state (``now < expiresAt`` on the latest row — no expiry job, BR-SB2) and is total: any
repository/lookup failure yields the free values instead of raising (BR-SB5 fail-safe).

Audit (SEC-14) follows the accounts idiom — append-only STRUCTURED LOG records
(``log.info({"event": ...})``); a dedicated audit store remains deferred infrastructure.
Grant/revoke audit immediately; the expiry transition audits exactly once on the first
post-expiry resolution, idempotent via the persisted ``expiryNotedAt`` marker (BR-SB6).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from .models import (
    FREE_TIER,
    PlanAssignment,
    PlanTier,
    add_one_month,
    utc_now,
)
from .repository import PlanRepository

log = logging.getLogger("docsuri.backend.plans")

# Defaults per functional-design §2: plus = 3× free (spend report §2 — worst case ~$378/mo
# per user), recalibrated without code via env; free values reuse the EXISTING agent-quota
# env knobs so the two layers can never disagree about what "free" means.
_DEFAULT_PLUS_EVIDENCE_DAILY = 90
_DEFAULT_PLUS_NOVELTY_DAILY = 15
_DEFAULT_FREE_EVIDENCE_DAILY = 30
_DEFAULT_FREE_NOVELTY_DAILY = 5


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        log.warning("plans: invalid %s ignored (default %s)", name, default)
        return default


@dataclass(frozen=True)
class PlansConfig:
    """Quota value knobs (nfr-requirements §env) — read per service construction so an env
    change lands on restart with zero code (§6 무코드 캘리브레이션)."""

    plus_evidence_daily: int = _DEFAULT_PLUS_EVIDENCE_DAILY
    plus_novelty_daily: int = _DEFAULT_PLUS_NOVELTY_DAILY
    free_evidence_daily: int = _DEFAULT_FREE_EVIDENCE_DAILY
    free_novelty_daily: int = _DEFAULT_FREE_NOVELTY_DAILY

    @classmethod
    def from_env(cls) -> PlansConfig:
        return cls(
            plus_evidence_daily=_env_int(
                "DOCSURI_PLAN_PLUS_EVIDENCE_DAILY", _DEFAULT_PLUS_EVIDENCE_DAILY
            ),
            plus_novelty_daily=_env_int(
                "DOCSURI_PLAN_PLUS_NOVELTY_DAILY", _DEFAULT_PLUS_NOVELTY_DAILY
            ),
            free_evidence_daily=_env_int(
                "DOCSURI_AGENT_EVIDENCE_DAILY_LIMIT", _DEFAULT_FREE_EVIDENCE_DAILY
            ),
            free_novelty_daily=_env_int(
                "DOCSURI_AGENT_NOVELTY_DAILY_LIMIT", _DEFAULT_FREE_NOVELTY_DAILY
            ),
        )


@dataclass(frozen=True)
class QuotaResolution:
    """Outcome of one plan resolution — consumed by /plans/me and the agent-quota shim."""

    tier: str  # "free" | "plus"
    evidence_daily: int
    novelty_daily: int
    expires_at: datetime | None = None


class PlansService:
    def __init__(self, repo: PlanRepository, *, config: PlansConfig | None = None) -> None:
        self._repo = repo
        self._config = config or PlansConfig.from_env()

    # ── admin grant/revoke (US-SB2/SB3, BR-SB4 enforced at the controller) ───────────────

    def grant(self, admin_id: str, user_id: str, now: datetime | None = None) -> PlanAssignment:
        """New append-only row, monthly period (startsAt + 1 calendar month). A re-grant of
        an already-plus user is simply a fresh row — the latest row governs (BR-SB2)."""
        now = now or utc_now()
        assignment = PlanAssignment(
            userId=user_id,
            tier=PlanTier.PLUS,
            startsAt=now,
            expiresAt=add_one_month(now),
            grantedBy=admin_id,
            createdAt=now,
        )
        created = self._repo.add_assignment(user_id, assignment)
        # SEC-14: 추가전용 감사 로그(구조화 로그로 기록 — accounts 전례; 전용 스토어는 이월).
        log.info(
            {
                "event": "PlanGranted",
                "assignmentId": created.id,
                "userId": user_id,
                "grantedBy": admin_id,
                "startsAt": created.startsAt.isoformat(),
                "expiresAt": created.expiresAt.isoformat(),
            }
        )
        return created

    def revoke(
        self, admin_id: str, user_id: str, now: datetime | None = None
    ) -> PlanAssignment | None:
        """Mark ``revokedAt`` on the active row — paid-through-period: plus keeps running
        until ``expiresAt`` (US-SB3/BR-SB2). None when there is nothing active to revoke."""
        now = now or utc_now()
        revoked = self._repo.mark_revoked(user_id, now)
        if revoked is not None:
            log.info(
                {
                    "event": "PlanRevoked",
                    "assignmentId": revoked.id,
                    "userId": user_id,
                    "revokedBy": admin_id,
                    "revokedAt": now.isoformat(),
                    "effectiveUntil": revoked.expiresAt.isoformat(),
                }
            )
        return revoked

    # ── quota resolution (US-SB1, the §2 supply shim's single source) ────────────────────

    def resolve_quotas(self, user_id: str, now: datetime | None = None) -> QuotaResolution:
        """Total function — NEVER raises (BR-SB5): any repository failure degrades to the
        free values so a plan-store outage cannot block an agent request. The first
        resolution after a row expires emits the deferred expiry audit exactly once,
        idempotent via the persisted ``expiryNotedAt`` marker (BR-SB6)."""
        config = self._config
        free = QuotaResolution(
            tier=FREE_TIER,
            evidence_daily=config.free_evidence_daily,
            novelty_daily=config.free_novelty_daily,
        )
        try:
            now = now or utc_now()
            latest = self._repo.latest_assignment(user_id)
            if latest is None:
                return free  # BR-SB1: no row = free — the default state, zero migration
            if now < latest.expiresAt:
                return QuotaResolution(
                    tier=PlanTier.PLUS.value,
                    evidence_daily=config.plus_evidence_daily,
                    novelty_daily=config.plus_novelty_daily,
                    expires_at=latest.expiresAt,
                )
            if latest.expiryNotedAt is None and self._repo.mark_expiry_noted(latest.id, now):
                log.info(
                    {
                        "event": "PlanExpired",
                        "assignmentId": latest.id,
                        "userId": user_id,
                        "expiresAt": latest.expiresAt.isoformat(),
                        "notedAt": now.isoformat(),
                    }
                )
            return free
        except Exception:  # noqa: BLE001 — BR-SB5: resolution failure must not block requests
            log.warning("plans: quota resolution failed — free fail-safe", exc_info=True)
            return free

    # ── spend rollup (BR-SB7 — observation only, never enforcement) ──────────────────────

    def record_spend_rollup(
        self, user_id: str, module: str, usd: float, now: datetime | None = None
    ) -> None:
        """Upsert-add one (user, UTC date, module) row. Best-effort by contract: NEVER
        raises into the caller — a rollup failure must not affect the turn/job (BR-SB7)."""
        try:
            if not user_id or usd <= 0:
                return
            now = now or utc_now()
            self._repo.add_spend(user_id, now.date(), module, float(usd), now)
        except Exception:  # noqa: BLE001 — observation-only, dropped on failure
            log.warning("plans: spend rollup dropped (observation-only)", exc_info=True)
