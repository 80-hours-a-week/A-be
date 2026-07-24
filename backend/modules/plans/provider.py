"""U16 Plans — process-wide repository scope for out-of-request consumers.

The controller gets its repo through FastAPI DI (app-shell override, trends idiom). The two
OTHER consumers cannot: the agent-quota middleware resolves limits per request but outside
the plans router's DI graph, and the evidence/novelty WORKER processes never run the
app-shell at all. Both go through this module-level seam — mirroring how the middleware
already obtains shared state (``rate_limit.get_shared_limiter``).

The app-shell wires the SAME repo source here as into the controller DI at mount time, so an
admin grant is visible to the middleware immediately (in-memory mode shares the one repo
instance; postgres shares the database). Unwired processes (workers, bare tests) lazily fall
back to an env-driven default: postgres DSN → own engine + session-per-scope, else a
process-local in-memory repo. Every failure mode here surfaces to callers who already
fail-safe to free values (BR-SB5) or drop the observation (BR-SB7).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from threading import RLock

from .repository import InMemoryPlanRepository, PlanRepository
from .service import PlansService, QuotaResolution

log = logging.getLogger("docsuri.backend.plans")

RepoScopeFactory = Callable[[], AbstractContextManager[PlanRepository]]

_lock = RLock()
_scope_factory: RepoScopeFactory | None = None


def set_repo_scope_factory(factory: RepoScopeFactory | None) -> None:
    """Wire (app-shell mount / tests) or reset (None → rebuild the lazy default)."""
    global _scope_factory
    with _lock:
        _scope_factory = factory


def _postgres_scope_factory(database_url: str) -> RepoScopeFactory:
    from backend.db import make_engine, make_session_factory

    from .repository import SqlPlanRepository

    session_factory = make_session_factory(make_engine(database_url))

    @contextmanager
    def scope() -> Iterator[PlanRepository]:
        session = session_factory()
        try:
            yield SqlPlanRepository(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def _memory_scope_factory() -> RepoScopeFactory:
    repo = InMemoryPlanRepository()

    @contextmanager
    def scope() -> Iterator[PlanRepository]:
        yield repo

    return scope


def _build_default_factory() -> RepoScopeFactory:
    try:
        from backend.config import Settings

        database_url = Settings.from_env().database_url
    except Exception:  # noqa: BLE001 — config unavailable → memory fallback
        database_url = ""
    if database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        log.info("plans: provider default = sql(postgres)")
        return _postgres_scope_factory(database_url)
    log.info("plans: provider default = in-memory")
    return _memory_scope_factory()


def _get_scope_factory() -> RepoScopeFactory:
    global _scope_factory
    with _lock:
        if _scope_factory is None:
            _scope_factory = _build_default_factory()
        return _scope_factory


def resolve_quotas_for(user_id: str) -> QuotaResolution:
    """One plan resolution against the process-wide repo source. The service inside is
    total (free fail-safe); scope construction failures raise to the caller, who treats
    any error as free values (agent_quota._plan_limit)."""
    with _get_scope_factory()() as repo:
        return PlansService(repo).resolve_quotas(user_id)


def record_spend_for(user_id: str, module: str, usd: float) -> None:
    """One rollup write against the process-wide repo source (workers via rollup.py)."""
    with _get_scope_factory()() as repo:
        PlansService(repo).record_spend_rollup(user_id, module, usd)
