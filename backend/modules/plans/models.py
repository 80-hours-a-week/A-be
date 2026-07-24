"""U16 Plans — domain models + request/response DTOs (functional-design §1/§3).

PlanAssignment is an APPEND-ONLY history: a grant inserts a new row, a revoke only MARKS
``revokedAt`` (paid-through-period — the effect keeps running until ``expiresAt``, BR-SB2),
and a re-grant is a fresh row. free is the absence of any row (BR-SB1) — there is no "free"
assignment to migrate existing users onto. ``expiryNotedAt`` is the idempotency marker for
the one-shot deferred expiry audit (BR-SB6). UserDailySpend is observation-only calibration
data (spend report recommendation #2) and participates in NO enforcement (BR-SB7).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def add_one_month(moment: datetime) -> datetime:
    """Calendar-month period end (OQ-6 monthly grants): same day next month, clamped to the
    target month's last day (Jan 31 → Feb 28/29). Stdlib-only — no new dependency."""
    year = moment.year + (moment.month // 12)
    month = moment.month % 12 + 1
    day = min(moment.day, monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


class PlanTier(StrEnum):
    # free intentionally has NO member: free = row absence (BR-SB1), never a stored value.
    PLUS = "plus"


FREE_TIER = "free"  # response-only label — never persisted


class PlanAssignment(BaseModel):
    id: str = Field(default_factory=new_id)
    userId: str
    tier: PlanTier = PlanTier.PLUS
    startsAt: datetime
    expiresAt: datetime
    revokedAt: datetime | None = None
    grantedBy: str
    expiryNotedAt: datetime | None = None
    createdAt: datetime = Field(default_factory=utc_now)


class UserDailySpend(BaseModel):
    """One (user, UTC date, module) rollup row — ``usd`` is upsert-added (BR-SB7)."""

    userId: str
    date: date
    module: str
    usd: float = 0.0
    updatedAt: datetime = Field(default_factory=utc_now)


# ── Request/response DTOs (boundary validation — strict, extra forbidden) ────────────────────


class GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str = Field(min_length=1, max_length=64)

    @field_validator("userId")
    @classmethod
    def _valid_uuid(cls, value: str) -> str:
        # Principal user ids are UUIDs everywhere (docsuri_shared.authz) — fail fast at the
        # boundary with a schema 422 instead of writing an unreachable assignment row.
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("userId must be a UUID") from exc
        return value


class PlanQuotas(BaseModel):
    evidenceDaily: int
    noveltyDaily: int


class PlanMeResponse(BaseModel):
    """US-SB1 — own tier + today's quota values (+ expiry when plus). Owner-scoped (SEC-8);
    carries nothing about other users or internal assignment history (SEC-9)."""

    tier: str
    quotas: PlanQuotas
    expiresAt: datetime | None = None


class GrantResponse(BaseModel):
    userId: str
    tier: str
    startsAt: datetime
    expiresAt: datetime
    revokedAt: datetime | None = None
