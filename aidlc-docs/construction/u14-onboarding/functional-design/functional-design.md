# U14 Onboarding — Functional Design

> **상태**: 🟡 DRAFT 제안 (2026-07-23) · **SSOT 입력**: `inception/requirements/onboarding.md`(RESOLVED)·`requirements.md` FR-44~46·C-7/C-8·FR-39 개정 · `stories.md` 에픽 12 US-OB1~4 · `unit-of-work.md` U14 · U9 `functional-design/domain-entities.md`(BehaviorEvent 계약)
> U14는 U9보다 훨씬 작은 유닛이라 domain-entities/business-rules/business-logic을 본 파일 하나로 통합한다. U9 소유 계약(BehaviorEvent·프로필 집계)은 여기서 재정의하지 않고 참조만 한다.

## 1. Entity Model

### InterestSelection *(transient — FE/요청 스코프, 영속 없음)*
- `categories: list[str]` — arXiv 카테고리 ID (픽커 선택)
- `keywords: list[str]` — ORCID 저작 유도 키워드 (픽커 단독 경로에서는 빈 목록)
- `source: "onboarding_picker" | "orcid_derived"`

### BehaviorEventType 확장 *(U9 소유 — 본 트랙에서 U9에 추가)*
- **`interest_set`** *(신규 — FR-39 개정)*: 사용자가 관심사를 직접 설정한 의미 있는 행동. metadata:
  - `source`: `"onboarding_picker" | "orcid_derived"`
  - `categories: list[str]`, `keywords: list[str]`
- 기존 kind(`search_executed` 등)와 동일한 owner-scoped·90일 보관·dedupe 계약을 그대로 따른다.

### OnboardingStatus *(U14 소유 — 재프롬프트 방지)*
- `userId` (owner-scoped, SEC-8) · `state: "pending" | "completed" | "skipped"` · `promptedAt`
- `skipped`는 프로필에 아무 흔적을 남기지 않는 UI 상태다 — 행동 이벤트가 **아니며** 집계에 관여하지 않는다.

## 2. 집계 매핑 *(U9 aggregator 확장 — 본 트랙에서 U9에 추가)*
- `interest_set.categories` → `categoryWeights` · `interest_set.keywords` → `keywordWeights`
- **시드 가중치**: `interest_set` 1건 = 카테고리당 `search_executed` **K배** 가중 (기본 **K=3**).
  <!-- ponytail: K=3 고정 상수 + env 오버라이드 knob — 실사용 감쇠 곡선이 이상하면 조정. 별도 감쇠 로직 없음: 90일 raw 보관이 감쇠를 대신한다(OQ-5 결정). -->
- **US-P5 선행**(본 트랙 포함, U9 소유): 라이브 부스트가 `categoryWeights`에 더해 `keywordWeights`를 소비하도록 확장 — 기존 `SEARCH_RERANK_LIVE` 게이트·fail-soft 계약 그대로.

## 3. API Surface *(U14 모듈, U6 게이트웨이 경유 — 제안)*
| Method | Path | 동작 |
|---|---|---|
| GET | `/onboarding/status` | `state` 반환 — FE가 픽커 노출 여부 결정 (US-OB1/OB2) |
| POST | `/onboarding/interests` | InterestSelection 검증(빈 선택 422·허용 카테고리 화이트리스트) → `interest_set` 이벤트 발행(비차단) → `state=completed` |
| POST | `/onboarding/skip` | `state=skipped` — 이벤트·프로필 무접촉 |
| GET | `/onboarding/orcid-suggestions` | ORCID 로그인 사용자 한정: 프로필·저작 조회 → 유도 관심사 제안(기록 없음 — 승인은 POST interests로) · 실패 시 빈 제안 + `degraded` 플래그 |

## 4. Flows
1. **신규 가입** (US-OB1): 가입 완료 → FE가 status 조회(`pending`) → 픽커 (ORCID 로그인이면 suggestions 선표시) → 선택 확정 → POST interests → 이벤트 발행 → 다음 집계에서 프로필 시딩.
2. **기존 사용자** (US-OB2): 로그인 → status `pending` → 동일 픽커 → 완료/스킵. `completed`/`skipped`면 프롬프트 없음.
3. **저하**: 이벤트 저장 실패 → 요청은 성공 응답 + 저하 신호(NFR-P4 — U9 기존 계약과 동일). ORCID 조회 실패 → 픽커-only (US-OB4).

## 5. Business Rules
- **BR-OB1**: 스킵/실패는 가입·로그인을 절대 막지 않는다 (NFR-P4).
- **BR-OB2**: 프로필 시딩은 `interest_set` 이벤트 경로 전용 — **직접 프로필 기록 금지** (C-7; TTL/재집계 소실 방지).
- **BR-OB3**: ORCID 유도 관심사는 **명시적 사용자 승인**(POST interests) 후에만 기록된다 — 제안 조회 자체는 무기록.
- **BR-OB4**: 픽커 프롬프트는 `state=pending`일 때만 — `skipped`는 재프롬프트하지 않는다. *(스킵 사용자의 사후 진입점(마이페이지 등)은 미결정 — 오너 후속 결정 후보, 여기서 발명하지 않음.)*
- **BR-OB5**: OnboardingStatus·유도 관심사 모두 owner-scoped (SEC-8).
- **BR-OB6**: 시드 이벤트는 기존 90일 보관·프로필 초기화·로그 삭제 계약에 그대로 걸린다 (QT-7 — 초기화 후 시딩 신호 제거).

## 6. Testable Properties
- 동일 `interest_set` 이벤트 집합 → 동일 시딩 프로필 (QT-7 결정성).
- 프로필 초기화 후 재집계 → 시딩 신호 부재.
- skip 멱등: 반복 POST skip이 상태·프로필을 변화시키지 않음.
- `interest_set` DTO 라운드트립 + 허용 카테고리 검증(화이트리스트 밖 422).
- ORCID 조회 실패 시 suggestions가 빈 제안 + degraded로 저하하고 200을 유지.

## 7. Traceability
FR-44(§3 status/interests·§4 flow 1~2) · FR-45(§1 interest_set·§2 매핑·BR-OB2/OB6) · FR-46(§3 orcid-suggestions·BR-OB3) · US-OB1~4(§4) · C-7(BR-OB2) · C-8(범위 — US-P5 §2) · NFR-P4(BR-OB1·§4 저하) · QT-7(§6) · SEC-8(BR-OB5)
