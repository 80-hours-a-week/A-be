"""U16 Plans — functional-design §6 testable properties.

Everything runs on in-memory fakes (no live DB/Redis): the middleware path uses the same
``InProcessWindowLimiter`` seam as the agent-quota suite, the plan store is the in-memory
repository, and the process-wide provider seam is pointed at it per test (and reset by an
autouse fixture). HTTP-facing properties (authz fail-closed, ADMIN gating, DTO bounds) run
through the app-shell TestClient like the U15 suite.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from docsuri_shared.authz import Principal, UserRole
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.middleware import agent_quota
from backend.middleware.rate_limit import InProcessWindowLimiter
from backend.modules.plans import controller, provider, rollup
from backend.modules.plans.models import add_one_month, utc_now
from backend.modules.plans.repository import InMemoryPlanRepository
from backend.modules.plans.service import PlansConfig, PlansService

T0 = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
CONFIG = PlansConfig()  # env-independent defaults: free 30/5, plus 90/15


def _principal(role: UserRole = UserRole.USER, *, mfa: bool = True) -> Principal:
    return Principal(user_id=str(uuid4()), role=role, mfa_verified=mfa)


def _request(user_id: str | None = "u1") -> SimpleNamespace:
    principal = SimpleNamespace(user_id=user_id) if user_id else None
    return SimpleNamespace(state=SimpleNamespace(principal=principal))


def _service(repo) -> PlansService:
    return PlansService(repo, config=CONFIG)


@pytest.fixture(autouse=True)
def _reset_plans_provider():
    # create_app (mount) and per-test wiring both mutate the module-level provider seam —
    # reset around every test so no factory leaks across tests.
    provider.set_repo_scope_factory(None)
    yield
    provider.set_repo_scope_factory(None)


@pytest.fixture()
def limiter(monkeypatch: pytest.MonkeyPatch) -> InProcessWindowLimiter:
    shared = InProcessWindowLimiter()
    monkeypatch.setattr(agent_quota, "get_shared_limiter", lambda: shared)
    return shared


@pytest.fixture()
def plans_repo() -> InMemoryPlanRepository:
    repo = InMemoryPlanRepository()

    @contextmanager
    def scope():
        yield repo

    provider.set_repo_scope_factory(scope)
    return repo


@contextmanager
def _broken_scope():
    raise RuntimeError("plan store down")
    yield  # pragma: no cover


class RaisingRepo:
    """Repository double whose lookups explode — BR-SB5 fail-safe fixture."""

    def latest_assignment(self, user_id: str):
        raise RuntimeError("boom")

    def commit(self) -> None:
        pass


# ── BR-SB1: no assignment = free (30/5) — 무회귀 ─────────────────────────────────────────────


def test_no_assignment_resolves_free_values() -> None:
    resolution = _service(InMemoryPlanRepository()).resolve_quotas(str(uuid4()), now=T0)
    assert resolution.tier == "free"
    assert (resolution.evidence_daily, resolution.novelty_daily) == (30, 5)
    assert resolution.expires_at is None


def test_middleware_free_user_enforced_with_module_constants(
    limiter, plans_repo, monkeypatch
) -> None:
    """US-SB1 무회귀: 미부여 사용자는 free 상수 그대로 집행 — plans가 배선돼 있어도 동일."""
    monkeypatch.setattr(agent_quota, "_EVIDENCE_DAILY_LIMIT", 2)

    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request()))
    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request()))
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(agent_quota.enforce_evidence_turn_quota(_request()))

    assert excinfo.value.status_code == 429


# ── US-SB2: grant → plus values enforced immediately through the middleware path ─────────────


def test_grant_takes_effect_immediately_through_middleware(
    limiter, plans_repo, monkeypatch
) -> None:
    monkeypatch.setattr(agent_quota, "_EVIDENCE_DAILY_LIMIT", 1)
    monkeypatch.setenv("DOCSURI_PLAN_PLUS_EVIDENCE_DAILY", "3")
    user, admin = str(uuid4()), str(uuid4())

    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))  # free: 1 allowed
    with pytest.raises(HTTPException):
        asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))

    PlansService(plans_repo).grant(admin, user)  # ← same repo the middleware resolves against

    # limiter mechanism unchanged (BR-SB3): the window already counted 2 — the plus limit of
    # 3 admits exactly one more request, then blocks again.
    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))
    with pytest.raises(HTTPException):
        asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))


def test_middleware_plan_resolution_runs_in_threadpool(limiter, plans_repo, monkeypatch) -> None:
    """NFR-P6/P7: 동기 플랜 해석(Postgres 배선 시 블로킹 DB 왕복)은 이벤트 루프에서 직접
    실행되지 않고 run_in_threadpool로 위임된다 — 요청마다 정확히 1회, 그리고 그 반환값이
    실제 집행 한도를 결정한다(plus 2가 free 1을 대체: 2회 통과 후 3회째 429)."""
    monkeypatch.setattr(agent_quota, "_EVIDENCE_DAILY_LIMIT", 1)
    monkeypatch.setenv("DOCSURI_PLAN_PLUS_EVIDENCE_DAILY", "2")
    recorded: list[tuple] = []
    real_run_in_threadpool = agent_quota.run_in_threadpool

    async def recording_run_in_threadpool(func, *args, **kwargs):
        recorded.append((func, args))
        return await real_run_in_threadpool(func, *args, **kwargs)

    monkeypatch.setattr(agent_quota, "run_in_threadpool", recording_run_in_threadpool)
    user, admin = str(uuid4()), str(uuid4())
    PlansService(plans_repo).grant(admin, user)

    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))
    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))  # free 1이면 여기서 429
    with pytest.raises(HTTPException):
        asyncio.run(agent_quota.enforce_evidence_turn_quota(_request(user)))

    assert recorded == [(agent_quota._plan_limit, ("evidence", user))] * 3


def test_plan_limit_resolves_both_scopes_for_plus(plans_repo) -> None:
    user, admin = str(uuid4()), str(uuid4())
    PlansService(plans_repo).grant(admin, user)
    assert agent_quota._plan_limit("evidence", user) == 90
    assert agent_quota._plan_limit("novelty", user) == 15
    assert agent_quota._plan_limit("evidence", str(uuid4())) is None  # free → None (상수 유지)


# ── BR-SB2/US-SB3: revoke marks only — paid-through-period ───────────────────────────────────


def test_revoke_mid_period_keeps_plus_until_expiry_then_free() -> None:
    repo = InMemoryPlanRepository()
    service = _service(repo)
    user, admin = str(uuid4()), str(uuid4())
    service.grant(admin, user, now=T0)  # expires Aug 1

    revoked = service.revoke(admin, user, now=T0 + timedelta(days=9))
    assert revoked is not None
    assert revoked.revokedAt == T0 + timedelta(days=9)
    assert revoked.expiresAt == add_one_month(T0)

    mid = service.resolve_quotas(user, now=T0 + timedelta(days=20))
    assert mid.tier == "plus"  # 기간 내 효력 유지 (paid-through-period)
    assert (mid.evidence_daily, mid.novelty_daily) == (90, 15)

    after = service.resolve_quotas(user, now=T0 + timedelta(days=40))
    assert after.tier == "free"
    assert (after.evidence_daily, after.novelty_daily) == (30, 5)

    # nothing active anymore → a second revoke has no target
    assert service.revoke(admin, user, now=T0 + timedelta(days=10)) is None


def test_add_one_month_clamps_to_month_end() -> None:
    assert add_one_month(datetime(2026, 1, 31, tzinfo=UTC)) == datetime(2026, 2, 28, tzinfo=UTC)
    assert add_one_month(datetime(2026, 12, 15, tzinfo=UTC)) == datetime(2027, 1, 15, tzinfo=UTC)


# ── BR-SB6: audit — immediate on grant/revoke, exactly-once deferred on expiry ───────────────


def _plan_events(caplog: pytest.LogCaptureFixture, event: str) -> list[dict]:
    return [
        record.msg
        for record in caplog.records
        if isinstance(record.msg, dict) and record.msg.get("event") == event
    ]


def test_grant_and_revoke_audit_immediately(caplog: pytest.LogCaptureFixture) -> None:
    repo = InMemoryPlanRepository()
    service = _service(repo)
    user, admin = str(uuid4()), str(uuid4())
    with caplog.at_level(logging.INFO, logger="docsuri.backend.plans"):
        service.grant(admin, user, now=T0)
        service.revoke(admin, user, now=T0 + timedelta(days=1))
    assert len(_plan_events(caplog, "PlanGranted")) == 1
    assert len(_plan_events(caplog, "PlanRevoked")) == 1


def test_first_post_expiry_resolution_audits_exactly_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = InMemoryPlanRepository()
    service = _service(repo)
    user, admin = str(uuid4()), str(uuid4())
    service.grant(admin, user, now=T0)
    after = T0 + timedelta(days=40)

    with caplog.at_level(logging.INFO, logger="docsuri.backend.plans"):
        first = service.resolve_quotas(user, now=after)
        again = service.resolve_quotas(user, now=after + timedelta(hours=1))
        # a FRESH service instance must not re-audit either — the marker is persisted state
        third = _service(repo).resolve_quotas(user, now=after + timedelta(days=1))

    assert first.tier == again.tier == third.tier == "free"
    assert len(_plan_events(caplog, "PlanExpired")) == 1


# ── BR-SB5: any resolution failure → free values, request succeeds ───────────────────────────


def test_repository_exception_yields_free_values() -> None:
    resolution = PlansService(RaisingRepo(), config=CONFIG).resolve_quotas(str(uuid4()))
    assert resolution.tier == "free"
    assert (resolution.evidence_daily, resolution.novelty_daily) == (30, 5)


def test_middleware_survives_plan_store_outage(limiter, monkeypatch) -> None:
    provider.set_repo_scope_factory(_broken_scope)
    monkeypatch.setattr(agent_quota, "_EVIDENCE_DAILY_LIMIT", 1)

    asyncio.run(agent_quota.enforce_evidence_turn_quota(_request("u-free")))  # succeeds
    with pytest.raises(HTTPException) as excinfo:  # free constant still enforced
        asyncio.run(agent_quota.enforce_evidence_turn_quota(_request("u-free")))
    assert excinfo.value.status_code == 429


# ── BR-SB7: spend rollup — upsert-add, attribution, never raises ─────────────────────────────


def test_rollup_accumulates_one_row_per_user_date_module() -> None:
    repo = InMemoryPlanRepository()
    service = _service(repo)
    user = str(uuid4())
    service.record_spend_rollup(user, "evidence", 0.25, now=T0)
    service.record_spend_rollup(user, "evidence", 0.5, now=T0 + timedelta(hours=2))
    service.record_spend_rollup(user, "novelty", 0.1, now=T0)

    evidence_row = repo.get_spend(user, T0.date(), "evidence")
    assert evidence_row is not None
    assert evidence_row.usd == pytest.approx(0.75)  # 가산 1행 — 행 증식 없음
    novelty_row = repo.get_spend(user, T0.date(), "novelty")
    assert novelty_row is not None
    assert novelty_row.usd == pytest.approx(0.1)


def test_worker_attribution_contextvar_feeds_rollup(plans_repo) -> None:
    user = str(uuid4())
    with rollup.spend_attribution(user):
        rollup.record_llm_spend("evidence", 0.2)
        rollup.record_llm_spend("evidence", 0.3)
    rollup.record_llm_spend("evidence", 9.9)  # unattributed context → observation skipped

    row = plans_repo.get_spend(user, utc_now().date(), "evidence")
    assert row is not None
    assert row.usd == pytest.approx(0.5)


def test_rollup_never_raises_even_when_provider_is_broken() -> None:
    provider.set_repo_scope_factory(_broken_scope)
    with rollup.spend_attribution(str(uuid4())):
        rollup.record_llm_spend("evidence", 0.2)  # must not raise (BR-SB7)


# ── env calibration (§6 무코드 캘리브레이션) ─────────────────────────────────────────────────


def test_env_overrides_change_plus_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCSURI_PLAN_PLUS_EVIDENCE_DAILY", "120")
    monkeypatch.setenv("DOCSURI_PLAN_PLUS_NOVELTY_DAILY", "40")
    repo = InMemoryPlanRepository()
    user, admin = str(uuid4()), str(uuid4())
    service = PlansService(repo)  # from_env at construction = restart-equivalent
    service.grant(admin, user, now=T0)

    resolution = service.resolve_quotas(user, now=T0 + timedelta(days=1))
    assert (resolution.evidence_daily, resolution.novelty_daily) == (120, 40)


# ── HTTP surface: mount, authz fail-closed, ADMIN gating (SEC-8/9, BR-SB4) ───────────────────


def _client(principal: Principal | None = None, repo=None) -> TestClient:
    app = create_app(Settings(env="test", database_url="sqlite://"))
    if principal is not None:
        app.dependency_overrides[controller.get_principal] = lambda: principal
    if repo is not None:
        app.dependency_overrides[controller.get_repo] = lambda: repo
    return TestClient(app)


def test_plans_mounts_in_app_shell() -> None:
    app = create_app(Settings(env="test", database_url="sqlite://"))
    assert "plans" in app.state.mount_result.mounted


def test_unauthenticated_requests_fail_closed_401() -> None:
    client = _client()  # no principal on request.state
    assert client.get("/plans/me").status_code == 401
    assert client.post("/plans/grants", json={"userId": str(uuid4())}).status_code == 401
    assert client.delete(f"/plans/grants/{uuid4()}").status_code == 401


def test_non_admin_grant_and_revoke_are_403() -> None:
    target = str(uuid4())
    user_client = _client(_principal(UserRole.USER))
    assert user_client.post("/plans/grants", json={"userId": target}).status_code == 403
    assert user_client.delete(f"/plans/grants/{target}").status_code == 403

    # ops precedent (BR-A7): ADMIN without MFA is denied with the same generalized 403
    no_mfa_client = _client(_principal(UserRole.ADMIN, mfa=False))
    response = no_mfa_client.post("/plans/grants", json={"userId": target})
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_grant_dto_bounds_yield_422() -> None:
    admin_client = _client(_principal(UserRole.ADMIN))
    assert admin_client.post("/plans/grants", json={}).status_code == 422
    assert admin_client.post("/plans/grants", json={"userId": "not-a-uuid"}).status_code == 422
    assert (
        admin_client.post(
            "/plans/grants", json={"userId": str(uuid4()), "extra": 1}
        ).status_code
        == 422
    )  # extra=forbid


def test_me_grant_revoke_http_flow() -> None:
    repo = InMemoryPlanRepository()
    user = _principal(UserRole.USER)
    admin_client = _client(_principal(UserRole.ADMIN), repo=repo)
    user_client = _client(user, repo=repo)

    free_view = user_client.get("/plans/me")
    assert free_view.status_code == 200
    assert free_view.json()["tier"] == "free"
    assert free_view.json()["quotas"] == {"evidenceDaily": 30, "noveltyDaily": 5}
    assert free_view.json()["expiresAt"] is None

    granted = admin_client.post("/plans/grants", json={"userId": user.user_id})
    assert granted.status_code == 201
    assert granted.json()["tier"] == "plus"
    assert granted.json()["revokedAt"] is None

    plus_view = user_client.get("/plans/me").json()
    assert plus_view["tier"] == "plus"
    assert plus_view["quotas"] == {"evidenceDaily": 90, "noveltyDaily": 15}
    assert plus_view["expiresAt"] is not None  # US-SB1: plus면 만료일 노출

    revoked = admin_client.delete(f"/plans/grants/{user.user_id}")
    assert revoked.status_code == 200
    assert revoked.json()["revokedAt"] is not None
    # paid-through-period: the revoked user keeps plus until expiry (BR-SB2)
    assert user_client.get("/plans/me").json()["tier"] == "plus"

    # nothing active to revoke anymore → generalized 404 (SEC-9)
    assert admin_client.delete(f"/plans/grants/{user.user_id}").status_code == 404


def test_me_survives_repository_failure_with_free_view() -> None:
    user_client = _client(_principal(UserRole.USER), repo=RaisingRepo())
    response = user_client.get("/plans/me")
    assert response.status_code == 200  # BR-SB5: 저장소 장애도 free 뷰로 성공
    assert response.json()["tier"] == "free"
    assert response.json()["quotas"] == {"evidenceDaily": 30, "noveltyDaily": 5}
