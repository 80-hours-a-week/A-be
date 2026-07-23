"""U15 Trends — domain models + request/response DTOs (functional-design §1/§4).

FollowedTopic carries its embedding IN THE ROW: it is produced ONCE at registration via the
injected embedding port (same model/space as the corpus) and would be refreshed only on a topic
text edit — the digest job never embeds (BR-TN7). DigestSettings holds the send watermark
(``lastSentAt``): the next digest contains only papers ingested after it, and an empty digest
never advances it (BR-TN2). Everything here is owner-scoped (SEC-8) and disjoint from U14/U9
interest data (BR-TN5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


# Small reasoned cap: 10 topics × per-topic match cap keeps the per-user digest work bounded
# and the follow list reviewable in the settings UI. Env-free by design — it is a product
# bound, not a calibration knob (those are T/N, service.TrendsConfig).
MAX_TOPICS_PER_USER = 10
MAX_TOPIC_LENGTH = 120


class DigestCadence(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class FollowedTopic(BaseModel):
    id: str = Field(default_factory=new_id)
    userId: str
    topic: str
    # JSON-serializable list — written once at registration (BR-TN7). Never exposed in DTOs.
    embedding: list[float] = Field(default_factory=list)
    createdAt: datetime = Field(default_factory=utc_now)


class DigestSettings(BaseModel):
    """Per-user digest opt-in row (BR-TN1: default opted OUT).

    ``lastSentAt`` is the send watermark; ``optedInAt`` anchors the FIRST send window (papers
    ingested after opt-in). ``updatedAt`` bumps ONLY on user-visible settings changes (PUT /
    unsubscribe) — it versions the signed unsubscribe token, so a settings change invalidates
    outstanding tokens (SEC-8) while a watermark advance keeps the token in the just-sent
    email valid.
    """

    userId: str
    optedIn: bool = False
    cadence: DigestCadence = DigestCadence.DAILY
    lastSentAt: datetime | None = None
    optedInAt: datetime | None = None
    updatedAt: datetime = Field(default_factory=utc_now)


class DigestSendRecord(BaseModel):
    """One row per delivered digest (§1 발송 이력) — observability/idempotency only; the email
    body itself is never stored."""

    id: str = Field(default_factory=new_id)
    userId: str
    sentAt: datetime
    paperCount: int


class PaperMatch(BaseModel):
    """A matched candidate paper from the search port. Deliberately carries NO abstract/body
    text: the digest email is link-back only (BR-TN6/C-1), so the type itself cannot leak
    corpus text into a rendered email."""

    paperId: str
    title: str
    score: float


# ── Request/response DTOs (boundary validation — strict, extra forbidden) ────────────────────


class FollowTopicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Field bounds run BEFORE validators (review SECURITY-05 precedent): an oversized payload
    # is rejected by the schema without entering custom code.
    topic: str = Field(min_length=1, max_length=MAX_TOPIC_LENGTH)

    @field_validator("topic")
    @classmethod
    def _stripped_non_empty(cls, topic: str) -> str:
        cleaned = " ".join(topic.split())
        if not cleaned:
            raise ValueError("topic must not be blank")
        return cleaned


class FollowedTopicResponse(BaseModel):
    """Public projection — the embedding is internal (SEC-9 style) and never serialized out."""

    id: str
    topic: str
    createdAt: datetime


class FollowListResponse(BaseModel):
    topics: list[FollowedTopicResponse]
    maxTopics: int = MAX_TOPICS_PER_USER


class DigestSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optedIn: bool
    cadence: DigestCadence = DigestCadence.DAILY


class DigestSettingsResponse(BaseModel):
    optedIn: bool
    cadence: DigestCadence
    lastSentAt: datetime | None


class UnsubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class UnsubscribeResponse(BaseModel):
    optedIn: bool


class DigestRunReport(BaseModel):
    """Outcome of one ``run_digest(now)`` sweep — per-user failure isolation means the loop
    always completes and this report is the only aggregate signal (BR-TN3)."""

    ranAt: datetime
    usersConsidered: int = 0
    sent: int = 0
    skippedNotDue: int = 0
    skippedEmpty: int = 0
    failed: int = 0
