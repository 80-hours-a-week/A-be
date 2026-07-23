# U14 Onboarding — NFR Requirements

> **상태**: 🟡 DRAFT 제안 (2026-07-23) · 신규 NFR 없음 — 기존 NFR의 U14 적용만 구체화한다 (`inception/requirements/onboarding.md` NFR 절 준수).

| 기존 NFR | U14 적용 |
|---|---|
| **NFR-P4** | 온보딩 API는 가입/로그인 크리티컬 패스 밖 — status 조회·이벤트 발행 실패가 세션 진입을 지연/차단하지 않는다. 이벤트 발행은 비차단(기존 U9 기록 계약 재사용). |
| **QT-7** | 시딩은 이벤트 경로 전용이므로 기존 불변식 테스트가 그대로 커버 — U14 추가분은 functional-design §6 Testable Properties. |
| **SEC-8** | OnboardingStatus·ORCID 유도 데이터 owner-scoped. ORCID 응답은 유도 관심사 추출 후 폐기 — 원본 저작 데이터 영속 저장 없음(제안). |

## 배포/인프라
- **신규 배포 단위 없음**: API 모듈(배포 ①) + FE 플로우(④) — `unit-of-work.md` U14 행 그대로.
- **신규 인프라 없음**: OnboardingStatus는 기존 Postgres에 소테이블 1개(마이그레이션 1건). 이벤트·프로필 저장소는 U9 소유 그대로. **로컬 서빙 환경**(compose PG/Redis/OpenSearch·Bedrock 원격)에서 추가 리소스 불요.
- **ORCID 외부 호출**: 기존 #347 OIDC 자격증명 재사용, 저하 fail-soft(픽커-only) — 신규 시크릿 없음(works 조회 스코프 추가 필요 여부는 구현 시 확인).

## 캘리브레이션
- 시드 가중치 K(기본 3, env 오버라이드): 실측 감쇠 곡선(시드 vs 행동 신호 교차 시점) 검토 후 조정 — functional-design §2.
