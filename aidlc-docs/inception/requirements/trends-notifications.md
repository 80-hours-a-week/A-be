# 트렌드/알림 (Trends & Notifications) — 요구사항 스펙

> **상태**: 🟢 RESOLVED — Open Questions **전건 결정(2026-07-23, 오너)** → 승인 게이트 통과, `requirements.md` **등재 완료**(FR-47~48·C-9~10) · **범위**: Phase 3 성장 스코프 2번 항목 · **유닛**: **U15(신규)** — OQ-7 결정
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §5.2·§1·§6 · roadmap 기재 운영 사실(daily harvest·`EMAIL_PROVIDER` 심 #348/#427) · `hackathon-proposal.md` §문제 · 본 문서 §결정 기록 오너 답변(2026-07-23)
> **ID 규약**: 마스터 시리즈 연속 — FR-47~48·C-9~10. 등재분이 SSOT이며 본 문서는 결정 경위를 보존한다.
> **⚠️ 실효 종속**: **daily harvest는 오너 결정으로 일시 중지**(OQ-5, CDK `ArxivDailySchedule` `enabled=False`) — U15는 구축 가능하나 **다이제스트에 담길 신규 논문은 harvest 재개 결정(추후 논의) 전까지 유입되지 않는다.**

## Functional Requirements

| ID | Requirement | Source | Acceptance |
|---|---|---|---|
| **FR-47** | **트렌드/알림 이메일 다이제스트 [U15]**: **옵트인**한 사용자(OQ-3)에게 팔로우 주제(FR-48)의 **신규 논문 plain list**(제목·초록 링크 — LLM 산출물 무포함, OQ-4)를 **기본 daily** 주기(사용자 설정 가능, OQ-2)로 발송한다. 논문 소스는 기존 daily harvest 산출물(C-9 — 현재 일시 중지), 매칭은 **키워드/임베딩 유사도**(OQ-8), 발송은 기존 `EMAIL_PROVIDER` 경로 — **SES on `559352512800`**(OQ-6). | roadmap §5.2 · OQ-2/3/4/6/8 결정 | 옵트인하지 않은 사용자에게는 발송되지 않는다. 다이제스트 수록 논문은 harvest 신규분 중 수신자 팔로우 주제와 임베딩/키워드 유사도로 매칭된 것들이며 기존 코퍼스 정책(C-1/C-6) 안이다. 모든 다이제스트에 수신 해지 경로가 있고 해지는 즉시 반영된다. LLM 무포함이므로 NFR-C1 비대상. |
| **FR-48** | **팔로우 주제 목록 관리 [U15/U5]**: 사용자가 **명시적 팔로우 목록**(신설 — U14/U9 관심 프로필과 별개, OQ-1)을 만들고, **설정 UI**에서 팔로우 주제·발송 주기(기본 daily)·이메일 옵트인/해지를 관리한다(OQ-2/3). | OQ-1/2/3 결정 | 팔로우 목록·구독 상태는 owner-scoped(SEC-8)로 저장·조회·수정·삭제된다. 옵트인 전 기본값은 미발송이다. 설정 UI에서 주기 변경·옵트아웃이 즉시 반영된다. |

## Non-Functional Requirements

신규 NFR 없음 — 기존 NFR이 그대로 적용된다:

| 기존 ID | 적용 방식 |
|---|---|
| **SEC-8** | 팔로우 목록·구독 상태·발송 이력 owner-scoped 비공개. |
| **NFR-C1** | v1 다이제스트는 LLM 무포함(OQ-4 결정) → 비대상. 팔로우 주제 임베딩(OQ-8) 비용은 주제당 1회 수준 — 임계 아님. |
| **C-1/C-6** | 수록 논문은 기존 코퍼스 정책(OA 라이선스·AI/ML 범위) 준수, 원문 링크백. |

## Constraints

| ID | Kind | Constraint | Source |
|---|---|---|---|
| **C-9** | technical | 신규 파이프라인 금지 — 논문 소스는 기존 daily harvest 산출물, 발송은 기존 email 경로(`EMAIL_PROVIDER` 심)를 재사용한다. *(harvest는 현재 오너 결정으로 일시 중지 — 재개는 추후 논의.)* | roadmap §5.2 · OQ-5 결정 |
| **C-10** | business | Phase 3 실행 순서상 온보딩(완료) 다음, 구독제 앞 — 목적은 구독제가 전제하는 리텐션 루프 구축. | roadmap §5·§6 |

## 결정 기록 (Open Questions — 전건 RESOLVED 2026-07-23)

- [x] **OQ-1 · followed topics 정의** → **명시적 팔로우 목록 신설** (U14/U9 관심 프로필 재사용 아님 — FR-48).
- [x] **OQ-2 · 발송 주기** → **기본 daily, 설정 UI에서 사용자 관리**.
- [x] **OQ-3 · 옵트인** → **명시 옵트인** — 미옵트인 사용자 무발송 (정보통신망법 사전동의 정합·발신 평판 보호).
- [x] **OQ-4 · 내용 형태** → **plain list부터 시작** (신규 논문 제목·초록 링크; LLM 요약 없음 → NFR-C1 비대상).
- [x] **OQ-5 · 스케줄러** → **daily harvest 일시 중지, 추후 재논의** — CDK `ArxivDailySchedule` `enabled=False` 반영(본 커밋). 로컬 스택에는 harvest 스케줄러가 원래 없음(확인 — `ops/local/`은 백업 cron뿐). 다이제스트 잡 스케줄러 선택은 harvest 재개 논의와 함께 결정.
- [x] **OQ-6 · 이메일 프로바이더** → **SES on `559352512800`**. ⚠️ 운영 후속: 신규 계정 SES는 sandbox 시작 — production access 신청 필요, 로컬 서빙에는 task IAM role이 없으므로 자격증명 방식(스코프드 IAM) 설계 단계 확정.
- [x] **OQ-7 · 유닛 배치** → **신규 유닛 U15**.
- [x] **OQ-8 · 매칭 방식** → **키워드/임베딩 유사도** — 기존 코퍼스 임베딩 재사용, 팔로우 주제는 등록 시 임베딩.

---

**요약**: FR 2건(FR-47~48 등재) · 신규 NFR 0건 · 제약 2건(C-9~10 등재) · 미해결 질문 **0건**(8건 전건 결정) · 실효 종속 1건(harvest 재개 — 추후 논의). 최고 ID: FR-48 · C-10. **다음 단계: U15 사용자 스토리 → unit-of-work 등재 → 설계.**
