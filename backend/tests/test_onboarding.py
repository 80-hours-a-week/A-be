"""U14 Onboarding — functional-design §6 testable properties.

Seeding is event-path only (BR-OB2/C-7): every test reaches the U9 profile through
``interest_set`` events, never by writing the profile store. No live AWS/ORCID — the in-memory
repos and a monkeypatched ``fetch_orcid_public_record`` are the fake seams.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from docsuri_shared.authz import Principal, UserRole
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import create_app
from backend.config import Settings
from backend.modules.onboarding import controller
from backend.modules.onboarding.models import ALLOWED_CATEGORIES, InterestSelection
from backend.modules.onboarding.service import build_interest_event, derive_suggestions
from backend.modules.personalization import controller as personalization_controller
from backend.modules.personalization.models import (
    BehaviorEvent,
    BehaviorEventType,
    BehaviorSubject,
)
from backend.modules.personalization.repository import InMemoryPersonalizationRepository
from backend.modules.personalization.service import (
    BehaviorEventRecorder,
    PersonalizationReadPort,
    ProfileAggregator,
)


def _principal(user_id: str | None = None) -> Principal:
    return Principal(user_id=user_id or str(uuid4()), role=UserRole.USER)


def _client(
    principal: Principal | None = None,
    *,
    interest_recorder=None,
    account_repo=None,
) -> TestClient:
    app = create_app(Settings(env="test", database_url="sqlite://"))
    who = principal or _principal()
    app.dependency_overrides[controller.get_principal] = lambda: who
    app.dependency_overrides[personalization_controller.get_principal] = lambda: who
    if interest_recorder is not None:
        app.state.personalization_record_event = interest_recorder
    if account_repo is not None:
        app.dependency_overrides[controller.get_account_repo] = lambda: account_repo
    return TestClient(app)


def _recording_seam(p_repo: InMemoryPersonalizationRepository):
    """The app-shell seam shape: user_id + DTO → U9 EventRecordResult over a shared repo."""
    return lambda user_id, dto: BehaviorEventRecorder(p_repo).record(user_id, dto)


def _interest_event(
    user_id: str,
    categories: list[str],
    keywords: list[str],
    dedupe: str,
    occurred_at: datetime | None = None,
) -> BehaviorEvent:
    return BehaviorEvent(
        userId=user_id,
        eventType=BehaviorEventType.INTEREST_SET,
        subject=BehaviorSubject(kind="interest"),
        metadata={
            "source": "onboarding_picker",
            "categories": categories,
            "keywords": keywords,
        },
        dedupeKey=dedupe,
        occurredAt=occurred_at or datetime.now(UTC),
    )


def _search_event(
    user_id: str, top_categories: list[str], keywords: list[str], dedupe: str
) -> BehaviorEvent:
    return BehaviorEvent(
        userId=user_id,
        eventType=BehaviorEventType.SEARCH_EXECUTED,
        subject=BehaviorSubject(kind="search", queryHash=f"q-{dedupe}"),
        metadata={"topCategories": top_categories, "keywords": keywords},
        dedupeKey=dedupe,
        occurredAt=datetime.now(UTC) + timedelta(seconds=1),
    )


# ---------------------------------------------------------------------------
# InterestSelection DTO — roundtrip + whitelist (§6).
# ---------------------------------------------------------------------------


def test_interest_selection_dto_roundtrip() -> None:
    dto = InterestSelection(
        categories=["cs.AI", "cs.LG"], keywords=["transformer"], source="onboarding_picker"
    )

    again = InterestSelection.model_validate_json(dto.model_dump_json())

    assert again == dto
    assert again.categories == ["cs.AI", "cs.LG"]


def test_interest_selection_rejects_non_whitelist_and_empty() -> None:
    with pytest.raises(ValidationError):
        InterestSelection(categories=["cs.XX"])  # outside the C-6 corpus slice
    with pytest.raises(ValidationError):
        InterestSelection(categories=[], keywords=[])  # empty selection


def test_interest_selection_rejects_oversized_raw_arrays() -> None:
    # Field(max_length) fires before the dedupe validator — a flood is rejected up front
    # instead of paying the O(n) pass (unit review SECURITY-05).
    with pytest.raises(ValidationError):
        InterestSelection(categories=["cs.AI"] * 33)
    with pytest.raises(ValidationError):
        InterestSelection(categories=["cs.AI"], keywords=["transformers"] * 33)


def test_interest_selection_dedupes_repeated_picks() -> None:
    # A doubled pick must not double its seed weight in the aggregator.
    dto = InterestSelection(
        categories=["cs.AI", "cs.AI"], keywords=[" transformer ", "transformer"]
    )

    assert dto.categories == ["cs.AI"]
    assert dto.keywords == ["transformer"]


def test_api_interests_whitelist_violation_is_422() -> None:
    client = _client()

    assert (
        client.post("/onboarding/interests", json={"categories": ["math.OC"]}).status_code == 422
    )
    assert (
        client.post("/onboarding/interests", json={"categories": [], "keywords": []}).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Status / interests / skip flows (US-OB1/OB2, BR-OB4).
# ---------------------------------------------------------------------------


def test_status_defaults_to_pending_and_serves_allowed_categories() -> None:
    client = _client()

    body = client.get("/onboarding/status").json()

    assert body["state"] == "pending"
    assert body["categories"] == list(ALLOWED_CATEGORIES)


def test_interests_completes_and_emits_interest_set_event() -> None:
    p_repo = InMemoryPersonalizationRepository()
    principal = _principal()
    client = _client(principal, interest_recorder=_recording_seam(p_repo))

    resp = client.post(
        "/onboarding/interests",
        json={"categories": ["cs.AI"], "keywords": ["transformer"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"state": "completed", "eventRecorded": True, "reason": "recorded"}
    events = p_repo.list_events(principal.user_id)
    assert [e.eventType for e in events] == [BehaviorEventType.INTEREST_SET]
    assert events[0].metadata == {
        "source": "onboarding_picker",
        "categories": ["cs.AI"],
        "keywords": ["transformer"],
    }
    assert client.get("/onboarding/status").json()["state"] == "completed"


def test_identical_resubmit_dedupes_in_the_event_store() -> None:
    p_repo = InMemoryPersonalizationRepository()
    principal = _principal()
    client = _client(principal, interest_recorder=_recording_seam(p_repo))
    payload = {"categories": ["cs.AI"], "keywords": []}

    first = client.post("/onboarding/interests", json=payload).json()
    second = client.post("/onboarding/interests", json=payload).json()

    assert first["reason"] == "recorded"
    assert second == {"state": "completed", "eventRecorded": False, "reason": "duplicate"}
    assert len(p_repo.list_events(principal.user_id)) == 1


def test_interests_survives_event_store_failure() -> None:
    # NFR-P4: a down event store degrades the seed, never the request — mirrors U9 /events.
    def _boom(user_id, dto):
        raise RuntimeError("behavior-event store down")

    for recorder in (_boom, None):  # raising seam / seam not wired at all
        client = _client(interest_recorder=recorder)

        resp = client.post("/onboarding/interests", json={"categories": ["cs.LG"]})

        assert resp.status_code == 200
        assert resp.json() == {"state": "completed", "eventRecorded": False, "reason": "degraded"}
        assert client.get("/onboarding/status").json()["state"] == "completed"


def test_skip_is_idempotent_and_touches_no_events_or_profile() -> None:
    p_repo = InMemoryPersonalizationRepository()
    principal = _principal()
    client = _client(principal, interest_recorder=_recording_seam(p_repo))

    first = client.post("/onboarding/skip")
    second = client.post("/onboarding/skip")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"state": "skipped"}
    assert client.get("/onboarding/status").json()["state"] == "skipped"
    assert p_repo.list_events(principal.user_id) == []  # no behavior signal (BR-OB1)
    assert p_repo.get_profile(principal.user_id) is None  # no profile trace


def test_skip_after_completed_keeps_completed() -> None:
    # Completed wins: a stray skip must not mask already-seeded interests (re-prompt guard
    # only cares that state left `pending` — BR-OB4).
    client = _client()
    client.post("/onboarding/interests", json={"categories": ["cs.AI"]})

    resp = client.post("/onboarding/skip")

    assert resp.json() == {"state": "completed"}


# ---------------------------------------------------------------------------
# Seeding aggregation (QT-7: determinism, K-weighting, reset).
# ---------------------------------------------------------------------------


def test_seeding_is_deterministic_and_order_independent() -> None:
    user_id = str(uuid4())
    events = [
        _interest_event(user_id, ["cs.AI"], ["transformer"], "i1"),
        _interest_event(
            user_id, ["cs.LG"], ["diffusion"], "i2",
            occurred_at=datetime.now(UTC) + timedelta(seconds=5),
        ),
    ]

    profile = ProfileAggregator().aggregate(user_id, events)
    again = ProfileAggregator().aggregate(user_id, list(reversed(events)))

    assert profile is not None and again is not None
    assert profile.categoryWeights == again.categoryWeights
    assert profile.keywordWeights == again.keywordWeights


def test_interest_set_weighs_k_times_search_executed() -> None:
    # functional-design §2: one interest_set = K× a search_executed per category/keyword,
    # default K=3 → raw 1.5 vs 0.5 (categories) and 0.75 vs 0.25 (keywords); _bounded
    # normalizes to max=1.0, so the search signal lands at exactly 1/K of the seed.
    user_id = str(uuid4())
    events = [
        _interest_event(user_id, ["cs.AI"], ["transformer"], "i1"),
        _search_event(user_id, ["cs.LG"], ["diffusion"], "s1"),
    ]

    profile = ProfileAggregator().aggregate(user_id, events)

    assert profile is not None
    assert profile.categoryWeights["cs.AI"] == 1.0
    assert profile.categoryWeights["cs.LG"] == round(1 / 3, 4)
    assert profile.keywordWeights["transformer"] == 1.0
    assert profile.keywordWeights["diffusion"] == round(1 / 3, 4)


def test_seed_weight_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DOCSURI_ONBOARDING_SEED_WEIGHT", "5")
    user_id = str(uuid4())
    events = [
        _interest_event(user_id, ["cs.AI"], [], "i1"),
        _search_event(user_id, ["cs.LG"], [], "s1"),
    ]

    profile = ProfileAggregator().aggregate(user_id, events)

    assert profile is not None
    assert profile.categoryWeights["cs.LG"] == round(0.5 / 2.5, 4)  # K=5 → 1/K


def test_profile_reset_clears_seeded_signals() -> None:
    # BR-OB6/QT-7: seeded events ride the existing reset contract — after reset-profile the
    # seeding signal is gone until a NEW event arrives.
    p_repo = InMemoryPersonalizationRepository()
    user_id = str(uuid4())
    recorder = BehaviorEventRecorder(p_repo)
    recorder.record(
        user_id, build_interest_event(InterestSelection(categories=["cs.AI"], keywords=["gan"]))
    )

    assert PersonalizationReadPort(p_repo).search_decision(user_id).reason == "profile_available"
    p_repo.reset_profile(user_id)

    assert PersonalizationReadPort(p_repo).search_decision(user_id).reason == "no_profile"
    assert PersonalizationReadPort(p_repo).cached_search_boosts(user_id) == {}


def test_interest_event_dedupe_key_is_deterministic() -> None:
    same_a = build_interest_event(InterestSelection(categories=["cs.AI", "cs.LG"]))
    same_b = build_interest_event(InterestSelection(categories=["cs.AI", "cs.LG"]))
    other = build_interest_event(InterestSelection(categories=["cs.AI"]))

    assert same_a.dedupeKey == same_b.dedupeKey
    assert same_a.dedupeKey != other.dedupeKey


def test_seed_flows_into_search_decision_end_to_end(monkeypatch) -> None:
    # Whole seam: POST /onboarding/interests → wiring's personalization_record_event →
    # U9 aggregation → /decision/search serves category AND keyword boosts (US-P5).
    monkeypatch.setenv("PERSONALIZATION_ENABLED", "true")
    client = _client()

    submitted = client.post(
        "/onboarding/interests", json={"categories": ["cs.AI"], "keywords": ["transformer"]}
    ).json()
    decision = client.get("/api/personalization/decision/search").json()

    assert submitted == {"state": "completed", "eventRecorded": True, "reason": "recorded"}
    assert decision["reason"] == "profile_available"
    assert decision["searchBoosts"].get("cs.AI", 0.0) > 0.0
    assert decision["searchBoosts"].get("transformer", 0.0) > 0.0


# ---------------------------------------------------------------------------
# ORCID suggestions (FR-46/BR-OB3/US-OB4) — never 5xx, proposal only.
# ---------------------------------------------------------------------------


class _OrcidAccountRepo:
    """Fake of the U10 AccountRepository shape the controller consumes."""

    def __init__(self, orcid_id: str | None = None) -> None:
        self._orcid_id = orcid_id

    def get_orcid_identity(self, user_id: str):
        if self._orcid_id is None:
            return None
        return SimpleNamespace(orcid_id=self._orcid_id)


def test_orcid_suggestions_degrade_to_empty_on_failure(monkeypatch) -> None:
    async def _boom(orcid_id, **kw):
        raise RuntimeError("orcid down")

    monkeypatch.setattr(controller, "fetch_orcid_public_record", _boom)
    client = _client(account_repo=_OrcidAccountRepo("0000-0002-1825-0097"))

    resp = client.get("/onboarding/orcid-suggestions")

    assert resp.status_code == 200  # MUST never 5xx
    assert resp.json() == {"suggestions": [], "degraded": True}


def test_orcid_suggestions_empty_for_non_orcid_user() -> None:
    # Not a failure — a picker-only account simply has nothing to propose.
    client = _client(account_repo=_OrcidAccountRepo(None))

    resp = client.get("/onboarding/orcid-suggestions")

    assert resp.status_code == 200
    assert resp.json() == {"suggestions": [], "degraded": False}


def test_orcid_suggestions_degrade_when_lookup_seam_unwired() -> None:
    # sqlite/in-memory app-shell leaves get_account_repo at its None default → degraded.
    resp = _client().get("/onboarding/orcid-suggestions")

    assert resp.status_code == 200
    assert resp.json() == {"suggestions": [], "degraded": True}


def test_orcid_suggestions_derive_categories_and_keywords(monkeypatch) -> None:
    async def _fake_record(orcid_id, **kw):
        return {
            "affiliation": "Brown",
            "works": [
                {"title": "Neural Machine Translation with Transformers", "year": 2020},
                {"title": "Attention Networks for Neural Translation", "year": 2021},
            ],
        }

    monkeypatch.setattr(controller, "fetch_orcid_public_record", _fake_record)
    client = _client(account_repo=_OrcidAccountRepo("0000-0002-1825-0097"))

    body = client.get("/onboarding/orcid-suggestions").json()

    assert body["degraded"] is False
    categories = [s["value"] for s in body["suggestions"] if s["kind"] == "category"]
    keywords = [s["value"] for s in body["suggestions"] if s["kind"] == "keyword"]
    assert categories == ["cs.CL", "cs.LG"]  # translation → cs.CL, neural/networks → cs.LG
    assert set(categories) <= set(ALLOWED_CATEGORIES)  # never invents an off-slice category
    assert keywords[:2] == ["neural", "translation"]  # frequency first, then alphabetical


def test_derive_suggestions_is_deterministic_and_bounded() -> None:
    works = [{"title": f"Deep Learning for Topic {i} Analysis", "year": 2020} for i in range(30)]

    first = derive_suggestions(works)
    second = derive_suggestions(list(reversed(works)))

    assert first == second
    assert len([s for s in first if s.kind == "keyword"]) <= 10
