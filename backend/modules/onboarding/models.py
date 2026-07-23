"""U14 Onboarding — domain models + request/response DTOs.

InterestSelection is transient (functional-design §1): validated at the boundary, emitted as a
U9 ``interest_set`` event, never persisted here. OnboardingStatus is the only U14-owned state —
an owner-scoped re-prompt guard (BR-OB4/SEC-8), NOT a behavior signal (skip touches no profile).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


# C-6 corpus slice — the ONLY categories the picker may submit (whitelist; outside → 422).
# Single-sourced here and served by GET /onboarding/status so the FE needs no extra endpoint.
ALLOWED_CATEGORIES: tuple[str, ...] = ("cs.AI", "cs.CL", "cs.CV", "cs.LG", "stat.ML")

_MAX_KEYWORDS = 20
_MAX_KEYWORD_LENGTH = 64


class OnboardingState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class OnboardingStatus(BaseModel):
    userId: str
    state: OnboardingState = OnboardingState.PENDING
    promptedAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)


def _dedupe_clean(values: list[str]) -> list[str]:
    """Strip, drop empties, and dedupe preserving first occurrence — so a repeated pick cannot
    double its seed weight in the aggregator."""
    seen: dict[str, None] = {}
    for value in values:
        cleaned = value.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


class InterestSelection(BaseModel):
    """Picker/ORCID-derived selection (transient — request scope only)."""

    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source: Literal["onboarding_picker", "orcid_derived"] = "onboarding_picker"

    @field_validator("categories")
    @classmethod
    def _whitelisted(cls, categories: list[str]) -> list[str]:
        cleaned = _dedupe_clean(categories)
        unknown = [cat for cat in cleaned if cat not in ALLOWED_CATEGORIES]
        if unknown:
            raise ValueError(f"categories outside the corpus slice: {', '.join(sorted(unknown))}")
        return cleaned

    @field_validator("keywords")
    @classmethod
    def _bounded_keywords(cls, keywords: list[str]) -> list[str]:
        cleaned = _dedupe_clean(keywords)
        if len(cleaned) > _MAX_KEYWORDS:
            raise ValueError(f"too many keywords (max {_MAX_KEYWORDS})")
        if any(len(keyword) > _MAX_KEYWORD_LENGTH for keyword in cleaned):
            raise ValueError(f"keyword too long (max {_MAX_KEYWORD_LENGTH} chars)")
        return cleaned

    @model_validator(mode="after")
    def _non_empty(self) -> InterestSelection:
        if not self.categories and not self.keywords:
            raise ValueError("empty selection: pick at least one category or keyword")
        return self


class OnboardingStatusResponse(BaseModel):
    state: OnboardingState
    categories: list[str]  # the allowed picker categories (whitelist — see ALLOWED_CATEGORIES)


class InterestsResult(BaseModel):
    """POST /onboarding/interests outcome. ``eventRecorded=False`` + ``reason`` is the NFR-P4
    degrade signal: the state still completed, only the U9 seed event was dropped."""

    state: OnboardingState
    eventRecorded: bool
    reason: Literal["recorded", "duplicate", "disabled", "degraded"]


class SkipResult(BaseModel):
    state: OnboardingState


class OrcidSuggestion(BaseModel):
    kind: Literal["category", "keyword"]
    value: str


class OrcidSuggestionsResponse(BaseModel):
    """GET /onboarding/orcid-suggestions — proposal only (BR-OB3), never recorded here.
    ``degraded=True`` means the lookup path failed (US-OB4 → FE falls back to picker-only)."""

    suggestions: list[OrcidSuggestion] = Field(default_factory=list)
    degraded: bool = False
