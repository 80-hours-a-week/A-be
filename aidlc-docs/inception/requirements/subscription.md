# 구독제 (Subscription) — 요구사항 스펙

> **상태**: 🟡 DRAFT — Open Questions **오너 결정 대기** (승인 게이트; 결정 전 `requirements.md` 미등재) · **범위**: Phase 3 성장 스코프 4번(마지막) 항목 — 의도적으로 최후순위(roadmap §5.4·§6: 실측 비용 데이터 확보 후 가격 결정)
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §5.4·§6 · NFR-C1 비용 거버넌스 현황(PR #364 — CostGuard·per-user 쿼터) · `docsuri_shared.authz` UserRole 현황 · 로컬 서빙 시대 맥락(에필로그)
> **ID 규약**: 마스터 시리즈 연속 — 결정 후 **FR-50+(안)** 등재 예정 (현재 최고 ID: FR-49 · C-11).

## 배경 — 지금 있는 것

- **비용 거버넌스는 이미 사용자 단위로 작동한다**: `CostGuardCircuitBreaker` 공유 포트(U6 `CostGuardService` 구현), 에이전트 Bedrock 경로의 **실측 spend 기록**(invocation metrics), **per-user daily 쿼터**(evidence 30/day · novelty 5/day — Redis 공유, fail-open), critical-tier abstain 저하. **구독제의 자연스러운 미터링/집행 기반** — roadmap §5.4의 "agent LLM cost per user is the natural paid boundary"가 코드로 이미 존재한다.
- **계정에는 플랜 개념이 없다**: `UserRole = USER | ADMIN` 뿐(authz 계약, #167로 shared 이전). 티어/플랜은 신규 도메인이다.
- **가격 근거 데이터**: roadmap이 요구한 "real per-user Bedrock spend"는 CostGuard 기록 + KPI funnel(#346, U9 이벤트)로 존재 — 단, **로컬 서빙 전환 후의 실사용 규모는 팀 시대와 다르다**.
- **시대 맥락 (가장 중요한 전제 변화)**: 로드맵의 구독제 항목은 **AWS 프로덕션/팀 시대**(v1.19.0 이전)에 쓰였다. 현재는 **개인 포크·로컬 mac-mini 서빙** — 실결제 도입은 PG 심사·사업자 등록·세무 등 제품 밖 부담을 동반한다. **무엇을 위한 구독제인지가 첫 질문이다(OQ-1).**

## Proposed Functional Requirements *(골격 — OQ-1 결정이 형태를 정한다)*

| ID | Requirement (안) | 조건 |
|---|---|---|
| **FR-50(안)** | **플랜/티어 시스템 [유닛=OQ-7]**: 사용자마다 플랜(예: free/plus)이 있고, 플랜이 에이전트 쿼터(evidence·novelty daily)·기타 게이팅(OQ-2)을 결정한다. 기본값 free = 현행 쿼터 그대로(무회귀). 플랜 상태는 owner-scoped(SEC-8), 변경은 감사 로그(SEC-14). | OQ-1=(a)/(b) 공통 골격 |
| **FR-51(안)** | **결제/청구**: 페이먼트 프로바이더(OQ-4) 연동 — 구독 개시/갱신/실패/해지 라이프사이클, 청구 주기(OQ-6). 결제 실패·해지 시 다운그레이드 시맨틱(OQ-8). | **OQ-1=(a)일 때만** — (b)면 결제 없이 ADMIN 수동 플랜 부여로 대체 |

## 기존 NFR/제약 적용 *(예상)*

| 기존 ID | 적용 방식 |
|---|---|
| **SEC-8** | 플랜/구독 상태 owner-scoped 비공개. |
| **SEC-14** | 플랜 변경·결제 이벤트 감사 로그. |
| **SEC-9** | 결제 실패 등 에러는 일반화 응답 — PG 원시 응답·내부 상세 비노출. |
| **NFR-C1** | 구독제는 비용 거버넌스의 **수익 측면** — CostGuard 계약 불변, 플랜이 쿼터 값만 공급(집행 메커니즘 재사용). |
| **C-10** | Phase 3 순서 준수 — 리텐션 루프(U15) 이후 최후 항목(본 트랙). |

## Open Questions — 오너 결정 필요 ⬅ **승인 게이트**

- [ ] **OQ-1 · 목적/형태** *(가장 근본 — 나머지 OQ의 유효성을 정한다)*: (a) **실결제 구독** — PG 연동, 사업자/세무 부담 동반 (b) **플랜/티어 시스템만** — 쿼터·기능 게이팅 + ADMIN 수동 부여, 결제는 스텁/추후(로컬 서빙 시대에 자연스러운 축소) (c) **전체 유예** — Phase 3를 3/4 완료로 닫는다. *권고: (b) — 과금 경계·티어 도메인을 먼저 굳히면 (a)로의 승격은 PG 어댑터 추가일 뿐이다.*
- [ ] **OQ-2 · 유료(플랜) 경계**: 무엇이 상위 티어인가 — **에이전트 쿼터 상향**(evidence/novelty daily — roadmap §5.4의 자연 경계)만? 검색·요약·다이제스트는 전 티어 무료 유지?
- [ ] **OQ-3 · 티어 구조/수치**: free/plus 2단으로 시작? 수치(예: evidence 30→100/day, novelty 5→20/day)는 CostGuard 실측 spend로 캘리브레이션?
- [ ] **OQ-4 · 페이먼트 프로바이더** *(OQ-1=(a)일 때만)*: Stripe(글로벌, 구독 빌링 성숙) vs 국내 PG(토스페이먼츠 등 — 원화·국내 세무 정합). roadmap이 "requirements re-entry에서 결정"으로 미뤄둔 항목.
- [ ] **OQ-5 · 가격/수치 근거**: 결정 전에 **CostGuard 실측 per-user spend 리포트**(로컬 전환 후 구간)를 뽑아 검토하는 선행 단계를 둘까? (roadmap §5.4가 요구한 데이터 기반 결정)
- [ ] **OQ-6 · 청구 주기** *(OQ-1=(a)일 때만)*: 월간만? 연간 할인?
- [ ] **OQ-7 · 유닛 배치**: **신규 U16**(플랜/구독 도메인 — U14/U15 전례) vs U3(accounts) 확장. *권고: 신규 U16 — 계정 인증 도메인과 플랜/과금 도메인의 결합 회피.*
- [ ] **OQ-8 · 다운그레이드/해지 시맨틱**: 해지·결제 실패 시 즉시 free로? 지불 기간 만료까지 유지? 데이터는 전 티어 동일(쿼터만 변경) 확인.

---

**요약**: 제안 FR 2건 골격(FR-50~51안 — OQ-1이 형태 결정) · 신규 NFR 0건 예상 · **미해결 질문 8건 — 오너 결정 대기**. 결정 후: `requirements.md` 등재 → 스토리 → unit-of-work(OQ-7) → 설계.
