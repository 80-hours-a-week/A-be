"""NFR-C1 — 에이전트 경로 사용자별 일일 쿼터 (evidence turn / novelty job).

Bedrock 호출을 유발하는 진입점(research 메시지 추가·evidence 직접 턴, novelty job 생성)에
사용자별 하루 한도를 건다. 글로벌 cost guard(총액 캡)와 별개로, 단일 사용자의 폭주가
전체 예산을 소진하는 걸 막는 per-user 레이어다.

한도 초과는 429 — FE는 이미 429를 'rateLimited' UserFacingError로 매핑한다(errors.ts).
Redis 장애 시 limiter는 fail-open(가용성 우선) — 글로벌 cost guard가 백스톱.

U16 플랜-aware 해석(§2): limit "값"만 플랜 서비스로 요청별 해석한다 — 활성 plus면 plus 값
(DOCSURI_PLAN_PLUS_{EVIDENCE,NOVELTY}_DAILY), 아니면 아래 free 상수 그대로. 해석 실패는
전부 free 값 fail-safe(BR-SB5): plans 모듈 부재/미배선/저장소 장애 어느 경우에도 이 파일은
U16 이전과 동일하게 동작한다. 집행 메커니즘(limiter·키·윈도)은 무변경(NFR-C1).
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request

from backend.middleware.rate_limit import get_shared_limiter

log = logging.getLogger("docsuri.backend.agent_quota")

# FREE 기본값 — U16 이후에도 이 상수들이 free 티어의 유일한 출처다(BR-SB1 무회귀).
_EVIDENCE_DAILY_LIMIT = int(os.getenv("DOCSURI_AGENT_EVIDENCE_DAILY_LIMIT") or "30")
_NOVELTY_DAILY_LIMIT = int(os.getenv("DOCSURI_AGENT_NOVELTY_DAILY_LIMIT") or "5")
# ponytail: 첫 사용 기준 고정 24h 창(달력일 아님) — 달력일 리셋이 필요해지면 교체.
_WINDOW_SECONDS = 86_400
_QUOTA_MESSAGE = "오늘의 에이전트 사용 한도에 도달했습니다. 나중에 다시 시도해 주세요."


async def enforce_evidence_turn_quota(request: Request) -> None:
    await _enforce(request, scope="evidence", limit=_EVIDENCE_DAILY_LIMIT)


async def enforce_novelty_job_quota(request: Request) -> None:
    await _enforce(request, scope="novelty", limit=_NOVELTY_DAILY_LIMIT)


def _plan_limit(scope: str, user_id: str) -> int | None:
    """U16 §2 — 활성 plus 사용자의 plus 한도, 그 외 전부 None(→ 호출측 free 상수 유지).

    plans 모듈 부재·provider 미배선·저장소 예외 등 ANY 실패도 None: 미들웨어는 plans가
    없던 시절과 정확히 같게 동작해야 한다(BR-SB5 fail-safe, 무회귀)."""
    try:
        from backend.modules.plans.provider import resolve_quotas_for

        resolution = resolve_quotas_for(user_id)
    except Exception:  # noqa: BLE001 — 값 공급 실패는 조용히 free로
        log.debug("agent_quota: plan resolution unavailable — free limits", exc_info=True)
        return None
    if resolution.tier != "plus":
        return None
    return resolution.evidence_daily if scope == "evidence" else resolution.novelty_daily


async def _enforce(request: Request, *, scope: str, limit: int) -> None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return  # 인증 없음 → 라우트의 401이 담당, 쿼터는 관여하지 않는다
    plan_limit = _plan_limit(scope, principal.user_id)
    if plan_limit is not None:
        limit = plan_limit  # 활성 plus — 집행 메커니즘은 동일, 값만 교체(BR-SB3)
    key = f"agent:{scope}:{principal.user_id}"
    if not await get_shared_limiter().allow(key, limit=limit, window_seconds=_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail=_QUOTA_MESSAGE)
