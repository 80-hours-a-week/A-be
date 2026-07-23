# 트렌드/알림 (Trends & Notifications) — 요구사항 스펙

> **상태**: 🟡 DRAFT 제안 · **범위**: Phase 3 성장 스코프 2번 항목 — 현 frozen 범위 밖, `requirements.md` 등재 필요(승인 게이트 대기) · **일자**: 2026-07-23
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §5.2("email digest of new papers in followed topics. Cheapest version reuses the daily harvest + existing email path. Builds the retention loop 구독제 needs")·§1(트렌드/알림 ❌ Not started)·§6(순서 근거) · roadmap 기재 운영 사실(daily auto-harvest `docsuri-arxiv-daily` — AWS 시절 EventBridge 15:00 KST · email = `EMAIL_PROVIDER` SES 프라이머리/Resend 휴면 폴백, #348/#427) · `aidlc-docs/inception/plans/hackathon-proposal.md` §문제(트렌드 파악 불가 페인포인트) · U14/U9 관심 신호(`categoryWeights`·`keywordWeights` — FR-19·FR-44~46)
> **ID 규약**: 마스터 시리즈 연속 — 현재 최고치 FR-46·C-8 → 본 문서는 **FR-47·C-9~10 제안**. 승인 시 `requirements.md`에 등재.

## Functional Requirements

| ID | Requirement | Source | Acceptance |
|---|---|---|---|
| **FR-47** *(제안)* | **트렌드/알림 이메일 다이제스트**: 사용자가 팔로우하는 주제(followed topics — 정의는 **OQ-1**)의 **신규 논문**을 이메일 다이제스트로 발송한다. 신규 논문 소스는 **기존 daily harvest 산출물 재사용**, 발송은 **기존 email 경로 재사용**(`EMAIL_PROVIDER` 심 — #348). 구독제(§5.4)가 필요로 하는 리텐션 루프를 구축한다. | roadmap §5.2 · hackathon-proposal §문제 | 다이제스트에 담기는 논문은 daily harvest가 새로 수집한 논문 중 수신자의 followed topics에 매칭되는 것들이다(매칭 방식 OQ-8). 발송은 기존 email 경로를 그대로 타며 신규 발송 인프라를 만들지 않는다(C-9). 수신·구독 상태는 owner-scoped다(SEC-8). |

## Non-Functional Requirements

신규 NFR 없음 — 출처 문서에 트렌드/알림 고유의 비기능 요구가 명시되어 있지 않다. 기존 NFR이 그대로 적용된다:

| 기존 ID | 적용 방식 |
|---|---|
| **SEC-8** | followed topics·구독 상태·발송 이력 모두 owner-scoped 비공개 데이터. |
| **NFR-C1** | 다이제스트가 LLM 산출물(요약 등)을 포함하는 경우(OQ-4) 기존 비용 거버넌스 게이트 적용 — 단순 목록이면 비대상. |
| **C-1/C-6** | 다이제스트 수록 대상은 기존 코퍼스 정책(OA 라이선스·AI/ML 범위) 안의 논문으로 한정 — 원문 링크백 방식은 기존 디스커버리 표시 정책 준수. |

## Constraints

| ID | Kind | Constraint | Source |
|---|---|---|---|
| **C-9** *(제안)* | technical | 신규 파이프라인 금지 — 논문 소스는 기존 daily harvest 산출물, 발송은 기존 email 경로(`EMAIL_PROVIDER` 심)를 재사용한다. "Cheapest version"이 명시 요구다. | roadmap §5.2 |
| **C-10** *(제안)* | business | Phase 3 실행 순서상 온보딩(완료) 다음, 구독제 앞 — 본 기능의 목적은 구독제가 전제하는 **리텐션 루프** 구축이다. | roadmap §5·§6 |

## Open Questions

- [ ] **OQ-1 · "followed topics" 정의**: 명시적 팔로우 목록 신설인가, **U14/U9 관심 프로필 재사용**(`categoryWeights`/`keywordWeights` — 방금 시딩 가능해짐)인가, 혼합인가 — 미기재. U14 재사용이면 신규 UI 없이 성립한다.
- [ ] **OQ-2 · 발송 주기**: harvest는 일 1회 — 다이제스트도 daily인가, weekly 묶음인가, 사용자 설정인가 — 미기재.
- [ ] **OQ-3 · 옵트인/수신 동의**: 기본 발송 vs 명시 옵트인, unsubscribe 메커니즘(privacy/terms 페이지 #447과의 정합, 이메일 컴플라이언스) — 미기재.
- [ ] **OQ-4 · 다이제스트 내용 형태**: 신규 논문 목록(제목·초록 링크)만인가, LLM 요약/트렌드 코멘트 포함인가 — 포함 시 NFR-C1 비용 게이트 대상 — 미기재.
- [ ] **OQ-5 · 스케줄 실행 기반(로컬 서빙 시대)**: daily harvest 스케줄은 AWS 시절 EventBridge 15:00 KST — 로컬 스택에서 harvest가 현재 어떻게 도는지 확인 필요, 다이제스트 잡의 스케줄러 선택(compose cron 등) — 미기재.
- [ ] **OQ-6 · 이메일 프로바이더(로컬 서빙 시대)**: #348의 SES 프라이머리는 **이전 AWS 계정 task IAM role** 전제 — 개인 계정 559352512800에서 SES 재셋업인가, Resend 폴백 승격인가 — #348 결정의 로컬 시대 재검토 필요.
- [ ] **OQ-7 · 유닛 배치**: 신규 유닛(U15)인가, U6 ops 워커 확장인가, U1 harvest 후처리인가 — 미기재.
- [ ] **OQ-8 · 매칭 메커니즘**: harvest 신규 논문 ↔ followed topics 매칭이 카테고리 필터인가, 키워드/임베딩 유사도인가 — OQ-1 결정에 종속.

---

**요약**: FR 1건(FR-47 제안) · 신규 NFR 0건(SEC-8·NFR-C1·C-1/C-6 적용) · 제약 2건(C-9~10 제안) · 미해결 질문 8건. 최고 ID: FR-47 · C-10. **CONSTRUCTION 진입 전 Open Questions 전건 인간 결정 필요(승인 게이트).**
