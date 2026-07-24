# U16 Subscription/Plans — Functional Design

> **상태**: 🟡 DRAFT 제안 (2026-07-24) · **SSOT 입력**: `inception/requirements/subscription.md`(RESOLVED) · `requirements.md` FR-50~51·C-12 · `stories.md` 에픽 15 US-SB1~3 · `unit-of-work.md` U16 · `reports/costguard-spend-report-2026-07.md`(OQ-5 선행물)
> U14/U15 전례의 단일 파일 설계. **v1 결제 코드 없음**(C-12). **⚠️ plus 수치**: 스펜드 리포트 §2 기준 **3×(evidence 90/day·novelty 15/day)를 기본값으로 채택**(월 최악 ~$378/인) — env로 무코드 조정 가능, 오너가 2×를 원하면 env 변경만으로 족하다.

## 1. Entity Model *(전부 owner-scoped 조회, SEC-8)*

### PlanAssignment *(U16 소유 — append-only 이력)*
- `id` · `userId` · `tier: "plus"` (free는 **행 부재**가 기본 상태 — BR-SB1)
- `startsAt` · `expiresAt` (= startsAt + 1개월 — OQ-6 월 단위)
- `revokedAt: datetime | null` — 회수 **마킹**(즉시 효력 아님 — paid-through-period, BR-SB2)
- `grantedBy` (ADMIN userId) · `expiryNotedAt: datetime | null` (만료 감사 1회 기록용 마커, BR-SB6) · `createdAt`
- **활성 판정은 파생 상태**: `now < expiresAt` 인 최신 행 존재 = plus. **만료 잡·스케줄러 없음** — U15 OQ-5 교훈의 재적용: 로컬 서빙 시대에 배선할 스케줄러 자체가 없다. *(unit-of-work 행의 "만료 전환 잡" 표기는 본 설계로 정정 — 파생 상태가 잡을 대체한다.)*

### UserDailySpend *(스펜드 리포트 권고 #2 — 캘리브레이션 파이프라인)*
- `userId` · `date` · `module` (`evidence`|`novelty`|…) · `usd` (upsert 가산) · `updatedAt`
- `record_spend` 지점을 지나는 기존 `UsageEvent`를 1행으로 적재 — **관측 전용, 집행 불참여**(BR-SB7). v1 사용자 API 없음(운영자 조회/SQL).

## 2. 쿼터 공급 심 *(유일한 기존 코드 접점 — NFR-C1 계약 불변)*
- 현행: `backend/middleware/agent_quota.py` — `_enforce(request, scope, limit)`가 모듈 상수(`DOCSURI_AGENT_EVIDENCE_DAILY_LIMIT`=30 · `DOCSURI_AGENT_NOVELTY_DAILY_LIMIT`=5)를 사용, shared limiter(Redis) 집행, fail-open.
- 변경: limit 인자를 **플랜-aware 해석**으로 교체 — `PlanQuotaResolver.resolve(userId) → {evidence_daily, novelty_daily}`. 활성 plus 있으면 plus 값(`DOCSURI_PLAN_PLUS_EVIDENCE_DAILY` 기본 90 · `DOCSURI_PLAN_PLUS_NOVELTY_DAILY` 기본 15), 없으면 free 값(기존 env 상수 그대로).
- **해석 실패 = free 값 fail-safe**(BR-SB5): 플랜 조회 오류가 요청을 막지 않는다 — 카운터 집행의 기존 fail-open과 독립된, 값 공급 측의 안전 기본값. 집행 메커니즘(limiter·Redis 키·윈도)은 **무변경**.

## 3. API Surface *(U16 모듈, U6 게이트웨이 경유 — 제안)*
| Method | Path | 동작 |
|---|---|---|
| GET | `/plans/me` | 본인 플랜·쿼터·만료일 조회 (US-SB1, owner-scoped) |
| POST | `/plans/grants` | **ADMIN**: `{userId}`에 plus 부여 — 월 기간 개시 (US-SB2) |
| DELETE | `/plans/grants/{userId}` | **ADMIN**: 회수 — `revokedAt` 마킹(기간 말까지 효력 유지, 갱신 중단 의미) (US-SB3) |

결제·청구 엔드포인트 없음(C-12). ADMIN 판정은 기존 `docsuri_shared.authz` Guard(UserRole.ADMIN).

## 4. Business Rules
- **BR-SB1**: 미부여 = free = 현행 쿼터 — 행 부재가 기본 상태(무회귀). 기존 사용자 마이그레이션 불필요.
- **BR-SB2**: 활성 = 파생 상태(`now < expiresAt`) — 만료 잡 없음. 회수는 `revokedAt` 마킹뿐, 기간 내 효력 유지(paid-through-period). 재부여는 신규 행.
- **BR-SB3**: 플랜은 **쿼터 값만 공급** — CostGuard·limiter 집행 메커니즘 무변경(NFR-C1).
- **BR-SB4**: 부여/회수는 ADMIN 한정(authz Guard) — 비-ADMIN 403.
- **BR-SB5**: 플랜 해석 실패 시 free 값 fail-safe — 요청 비차단.
- **BR-SB6**: 감사(SEC-14) — 부여/회수 즉시 기록; 만료 전환은 만료 후 최초 해석 시 **1회 지연 기록**(`expiryNotedAt` 마커로 멱등).
- **BR-SB7**: UserDailySpend는 관측 전용 — 어떤 집행·차단에도 불참여.

## 5. FE *(U5/U10 mypage 표면 — 소규모)*
- 마이페이지에 **플랜 섹션**: 현재 티어(free/plus)·오늘 쿼터·(plus면) 만료일. `GET /plans/me` 소비. 결제 UI 없음(C-12).

## 6. Testable Properties
- 미부여 사용자 → free 값(30/5) 집행 + `/plans/me`가 free 반환 (US-SB1 무회귀).
- 부여 직후 → plus 값(90/15) 즉시 집행 — limiter 메커니즘 동일 (US-SB2).
- 비-ADMIN 부여/회수 → 403 (BR-SB4).
- 기간 중 회수 → 만료일까지 plus, 만료 후 free (US-SB3 paid-through-period).
- 만료 후 최초 해석 → 자동 free + 만료 감사 기록 정확히 1회(재해석에도 중복 없음) (BR-SB6).
- 플랜 저장소 장애 주입 → free 값으로 요청 성공 (BR-SB5).
- spend 롤업: 동일 (user,date,module) 반복 기록 → usd 가산 1행 (BR-SB7).
- env로 plus 수치 변경 → 재기동만으로 반영(무코드 캘리브레이션).

## 7. NFR 적용 *(신규 NFR 없음 — 상세 `../nfr-requirements/nfr-requirements.md`)*
SEC-8(owner-scoped `/plans/me`) · SEC-14(부여/회수/만료 감사) · SEC-9(일반화 에러) · NFR-C1(집행 계약 불변 — 값 공급만).

## 8. Traceability
FR-50(§1 PlanAssignment·§2 심·§5 FE·BR-SB1/3/5) · FR-51(§1 파생 만료·§3 grants·BR-SB2/4/6) · C-12(§3 결제 무표면) · US-SB1(§3 me·§5·§6) · US-SB2(§2·§3·§6) · US-SB3(§1·§6) · SEC-8/9/14(§3·§4) · NFR-C1(§2) · 스펜드 리포트 권고 #1(§ 헤더 3× 기본값)·#2(§1 UserDailySpend)·#3(§2 env 캘리브레이션)
