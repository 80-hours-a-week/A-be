"""U16 Plans — per-user Bedrock spend attribution for the daily rollup (BR-SB7).

Implementation choice (functional-design §1 UserDailySpend): the existing cost-guard
``record_spend`` call sites (evidence extractor, novelty LLM adapter) see the USD amount but
NOT the user — ``docsuri_ops.domain.models.UsageEvent`` carries no user context, and the ops
package is out of bounds for U16. So attribution rides a ``ContextVar``: the worker sets it
where the owner id IS in scope (``spend_attribution(owner_id)`` around job processing), and
the record sites tap it via ``record_llm_spend``. No attribution set → no rollup row —
observation quietly skips rather than guessing.

Everything here is best-effort by contract: ``record_llm_spend`` NEVER raises into the
caller — a rollup failure must not affect the turn/job (BR-SB7).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

log = logging.getLogger("docsuri.backend.plans")

_SPEND_USER: ContextVar[str | None] = ContextVar("docsuri_plans_spend_user", default=None)


@contextmanager
def spend_attribution(user_id: str | None) -> Iterator[None]:
    """Attribute Bedrock spend recorded inside this scope to ``user_id``."""
    token = _SPEND_USER.set(user_id)
    try:
        yield
    finally:
        _SPEND_USER.reset(token)


def current_spend_user() -> str | None:
    return _SPEND_USER.get()


def record_llm_spend(module: str, usd: float) -> None:
    """Roll ``usd`` into today's (user, module) row for the attributed user. Never raises
    (BR-SB7); without an attributed user (e.g. a code path that never set the context) the
    observation is skipped."""
    try:
        user_id = _SPEND_USER.get()
        if not user_id or usd <= 0:
            return
        from .provider import record_spend_for

        record_spend_for(user_id, module, float(usd))
    except Exception:  # noqa: BLE001 — observation-only, never into the caller
        log.warning("plans: spend rollup dropped (observation-only)", exc_info=True)
