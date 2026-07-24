# U16 Subscription/Plans — NFR Requirements

> **상태**: 🟡 DRAFT 제안 (2026-07-24) · 신규 NFR 없음 — 기존 NFR의 U16 적용만 구체화한다 (`inception/requirements/subscription.md` NFR 절 준수).

| 기존 NFR | U16 적용 |
|---|---|
| **SEC-8** | `/plans/me`는 본인 플랜만(owner-scoped). PlanAssignment·UserDailySpend 타인 조회 불가. |
| **SEC-14** | 부여/회수 즉시 감사, 만료 전환은 지연 1회 감사(`expiryNotedAt` 멱등 마커). |
| **SEC-9** | 플랜/부여 에러 일반화 응답 — 내부 상세·타 사용자 존재 여부 비노출. |
| **NFR-C1** | **집행 계약 불변** — limiter·CostGuard 메커니즘 무변경, 플랜은 limit 값 공급자. plus 기본 3×(90/15, 월 최악 ~$378/인 — 스펜드 리포트 §2) — env 조정으로 무코드 재캘리브레이션. |

## 배포/인프라
- **신규 배포 단위 없음**(API 모듈 ① 내). **스케줄러 없음** — 만료는 파생 상태(기능 설계 §1), 로컬 서빙 시대 정합.
- **마이그레이션 1건**: `plan_assignments` + `user_daily_spend` 테이블 2개 — 기존 마이그레이터 등록, 다음 스택 기동 시 자동 적용.
- **env**: `DOCSURI_PLAN_PLUS_EVIDENCE_DAILY`(기본 90) · `DOCSURI_PLAN_PLUS_NOVELTY_DAILY`(기본 15). free 값은 기존 `DOCSURI_AGENT_{EVIDENCE,NOVELTY}_DAILY_LIMIT` 재사용.

## 캘리브레이션
- plus 수치는 env — 스택 재기동 후 UserDailySpend 실측 2~4주 구간으로 스펜드 리포트 §2 가정 단가를 실측 대체, 필요시 수치 조정(무코드).
