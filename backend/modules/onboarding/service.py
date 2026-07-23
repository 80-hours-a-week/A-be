"""U14 Onboarding — service layer.

Profile seeding is EVENT-PATH ONLY (BR-OB2/C-7): this module never touches the U9 profile
store — it builds an ``interest_set`` DTO and hands it to the injected U9 recorder seam. Every
recorder failure degrades to a success-with-signal (NFR-P4: onboarding never blocks the session).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from hashlib import sha256

from backend.modules.personalization.models import (
    BehaviorEventCreate,
    BehaviorEventType,
    BehaviorSubject,
    EventRecordResult,
)

from .models import (
    ALLOWED_CATEGORIES,
    InterestSelection,
    OnboardingState,
    OnboardingStatus,
    OrcidSuggestion,
)
from .repository import OnboardingRepository

# user_id + interest_set DTO → U9 record outcome (wired by the app-shell; None = U9 off/absent).
InterestRecorder = Callable[[str, BehaviorEventCreate], EventRecordResult]


def _emit_metric(observability, name: str, value: float = 1.0, tags: dict | None = None) -> None:
    emit = getattr(observability, "emit_metric", None)
    if emit is None:
        return
    try:
        emit(name, value, tags or {})
    except Exception:
        pass


def build_interest_event(selection: InterestSelection) -> BehaviorEventCreate:
    """Deterministic ``interest_set`` DTO for a validated selection. The dedupe key hashes the
    SORTED selection, so re-submitting the identical picker state dedupes in the U9 store while
    a changed selection counts as a new signal (QT-7 seeding determinism)."""
    canonical = "|".join(sorted(selection.categories)) + "::" + "|".join(sorted(selection.keywords))
    digest = sha256(f"{selection.source}:{canonical}".encode()).hexdigest()[:16]
    return BehaviorEventCreate(
        eventType=BehaviorEventType.INTEREST_SET,
        subject=BehaviorSubject(kind="interest"),
        metadata={
            "source": selection.source,
            "categories": list(selection.categories),
            "keywords": list(selection.keywords),
        },
        dedupeKey=f"interest_set:{selection.source}:{digest}",
    )


class OnboardingService:
    def __init__(
        self,
        repo: OnboardingRepository,
        interest_recorder: InterestRecorder | None = None,
        observability=None,
    ) -> None:
        self._repo = repo
        self._interest_recorder = interest_recorder
        self._observability = observability

    def status(self, user_id: str) -> OnboardingStatus:
        """Current status; a user with no row is ``pending`` (no write on read — the status
        row appears on the first completed/skip transition)."""
        return self._repo.get_status(user_id) or OnboardingStatus(userId=user_id)

    def submit_interests(
        self, user_id: str, selection: InterestSelection
    ) -> tuple[OnboardingStatus, EventRecordResult]:
        """Emit the ``interest_set`` event (non-blocking) then mark the flow completed. The
        event outcome never gates the state transition: a down event store still completes
        onboarding and surfaces ``reason=degraded`` (NFR-P4 — mirrors U9's /events contract)."""
        record_result = self._record_interest(user_id, selection)
        status = self._repo.set_state(user_id, OnboardingState.COMPLETED)
        return status, record_result

    def skip(self, user_id: str) -> OnboardingStatus:
        """Idempotent skip — touches no events and no profile (BR-OB1/OB4). ``completed`` wins:
        a stray skip after a completed flow must not mask the already-seeded interests."""
        current = self._repo.get_status(user_id)
        if current is not None and current.state is not OnboardingState.PENDING:
            return current
        return self._repo.set_state(user_id, OnboardingState.SKIPPED)

    def _record_interest(self, user_id: str, selection: InterestSelection) -> EventRecordResult:
        if self._interest_recorder is None:
            return EventRecordResult(recorded=False, reason="degraded")
        try:
            return self._interest_recorder(user_id, build_interest_event(selection))
        except Exception:  # noqa: BLE001 — seeding is best-effort, never fails the request
            _emit_metric(self._observability, "onboarding.interest_event_failure")
            return EventRecordResult(recorded=False, reason="degraded")


# ── ORCID-derived suggestions (FR-46/BR-OB3 — proposal only, nothing recorded) ──────────────

# Function/framing words that carry no interest signal in a paper title. Domain nouns
# ("learning", "vision", …) are NOT stopwords — they drive the category hints below.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "into", "using", "via", "based", "towards",
        "toward", "are", "can", "not", "non", "between", "under", "over", "across",
        "through", "during", "without", "within", "how", "what", "when", "where", "which",
        "all", "new", "case", "study", "paper", "its", "our", "their", "this", "that",
        "these", "those",
    }
)

# Title-token → corpus-slice category hints (C-6). Deterministic tuple order; intentionally
# coarse — suggestions are user-approved before anything is recorded (BR-OB3), so precision
# matters less than never inventing a category outside ALLOWED_CATEGORIES.
_CATEGORY_HINTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("cs.AI", frozenset({"agent", "agents", "reasoning", "planning", "knowledge", "symbolic"})),
    ("cs.CL", frozenset({"language", "nlp", "translation", "text", "linguistic", "dialogue"})),
    ("cs.CV", frozenset({"vision", "image", "images", "video", "segmentation", "detection"})),
    ("cs.LG", frozenset({"learning", "neural", "network", "networks", "training", "deep"})),
    ("stat.ML", frozenset({"bayesian", "inference", "statistical", "probabilistic", "gaussian"})),
)
_MAX_SUGGESTED_KEYWORDS = 10


def derive_suggestions(works: list[dict]) -> list[OrcidSuggestion]:
    """Deterministic interest proposals from ORCID work titles: frequency-ranked title tokens
    become keyword suggestions; hint-matched tokens map to corpus-slice categories. Pure — the
    caller owns fetching and fail-soft degradation."""
    counts: Counter[str] = Counter()
    for work in works:
        title = str(work.get("title") or "")
        for token in re.findall(r"[a-z][a-z-]{2,}", title.lower()):
            if token not in _STOPWORDS:
                counts[token] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    keywords = [token for token, _ in ranked[:_MAX_SUGGESTED_KEYWORDS]]
    categories = [
        category
        for category, hints in _CATEGORY_HINTS
        if category in ALLOWED_CATEGORIES and hints & counts.keys()
    ]
    return [OrcidSuggestion(kind="category", value=category) for category in categories] + [
        OrcidSuggestion(kind="keyword", value=keyword) for keyword in keywords
    ]
