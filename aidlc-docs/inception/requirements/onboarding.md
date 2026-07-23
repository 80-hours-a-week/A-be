# 온보딩 (Onboarding) — 요구사항 스펙

> **상태**: 🟡 DRAFT 제안 · **범위**: Phase 3 성장 스코프 1번 항목 — 현 frozen 범위 밖, `requirements.md` 등재 필요(승인 게이트 대기) · **일자**: 2026-07-23
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §1(초기 계획 대비 현황: "온보딩 (고려) — Candidate fix for personalization cold-start")·§5.1("smallest scope; seeds U9 keyword signals at signup, solving personalization cold-start")·§6(순서 근거) · `aidlc-docs/inception/requirements/requirements.md` FR-19·FR-20·FR-39·NFR-P4·QT-7·§12 U9 제외 · `aidlc-docs/construction/u9-personalization/functional-design/domain-entities.md`(프로필 `categoryWeights`·`keywordWeights`)
> **ID 규약**: 마스터 시리즈 연속 — 현재 최고치 FR-43·C-6 → 본 문서는 **FR-44~45·C-7~8 제안**. 승인 시 `requirements.md`에 등재.

## Functional Requirements

| ID | Requirement | Source | Acceptance |
|---|---|---|---|
| **FR-44** *(제안)* | **가입 시 관심사 수집 [U10/U5]**: 신규 사용자 가입(signup) 플로우에서 연구 관심사 신호(키워드)를 수집한다. | roadmap §5.1 "seeds U9 keyword signals **at signup**" | 가입 플로우 안에서 관심사 입력 지점이 노출되고, 입력된 관심사가 FR-45의 시딩 입력으로 전달된다. 수집 실패/미입력이 가입 완료 자체를 막지 않는지는 **OQ-3**(스킵 가능 여부) 결정에 따른다. |
| **FR-45** *(제안)* | **U9 프로필 시딩 [U9]**: 수집된 관심사 신호로 U9 개인 관심사 프로필(FR-19)을 가입 직후 시딩하여, 행동 이벤트가 쌓이기 전에도 개인화 적용(FR-20)이 동작할 신호를 확보한다 — 개인화 콜드스타트 해소. | roadmap §1·§5.1 "solving personalization cold-start" | 관심사를 제공한 신규 사용자의 프로필에 시딩된 신호가 비어 있지 않고, 기존 FR-20 적용 경로(라이브 검색 부스트)가 **추가 랭킹 기계 신설 없이** 그 신호를 소비한다. 시딩된 신호도 FR-19의 사용자 통제(개인화 끄기·로그 삭제·프로필 초기화)에 똑같이 걸린다. |

## Non-Functional Requirements

신규 NFR 없음 — 출처 문서에 온보딩 고유의 비기능 요구가 명시되어 있지 않다. 기존 NFR이 그대로 적용된다:

| 기존 ID | 적용 방식 |
|---|---|
| **NFR-P4 [U9]** | 시딩 기록·집계가 가입 핵심 응답을 지연시키지 않고, 실패 시 비개인화 경로로 저하(가입은 성공). |
| **QT-7 [U9]** | 시딩이 프로필 집계 불변식(동일 입력 → 동일 프로필, 초기화 후 신호 제거)을 깨지 않아야 한다 — 시딩 메커니즘 결정(OQ-5)의 제약. |
| **SEC-8** | 시딩된 관심사도 owner-scoped 비공개 데이터. |

## Constraints

| ID | Kind | Constraint | Source |
|---|---|---|---|
| **C-7** *(제안)* | technical | 시딩은 기존 U9 프로필 저장·집계 계약 안에서 수행한다 — 별도 추천 목록·실시간 ML 파이프라인·강한 순위 변경 등 §12 U9 제외 항목을 재도입하지 않는다. | requirements.md §12 [U9 제외] |
| **C-8** *(제안)* | business | Phase 3 실행 순서상 온보딩이 첫 항목이다 — 트렌드/알림(리텐션 루프)·구독제(수익화)에 앞서, 개인화 콜드스타트 해소가 선행된다. | roadmap §5(권장 순서)·§6(순서 근거) |

## Open Questions

- [ ] **OQ-1 · 키워드 vs 카테고리 시딩**: roadmap은 "keyword signals"라 했지만, **라이브** 부스트(US-P4, v1.15.0)는 `categoryWeights`만 소비하고 `keywordWeights`는 US-P5(유예)다. 키워드만 시딩하면 US-P5 전까지 랭킹에 무효과 — 카테고리를 함께/대신 시딩할지, US-P5를 온보딩과 묶어 선행할지 결정 필요.
- [ ] **OQ-2 · 수집 UX**: 자유입력 키워드, arXiv 카테고리 픽커, 또는 혼합? 분류 체계(taxonomy) 출처는? — 출처 문서에 미기재.
- [ ] **OQ-3 · 스킵 가능 여부**: 관심사 입력이 가입 필수인지 스킵 가능인지, 가입 퍼널에 미치는 영향 허용치 — 미기재.
- [ ] **OQ-4 · 기존 사용자 소급**: 신규 가입자 전용인지, 기존 사용자에게도 다음 로그인 시 프롬프트할지 — 미기재.
- [ ] **OQ-5 · 시딩 메커니즘**: 합성 행동 이벤트로 FR-39 경로를 태울지(단, FR-39는 비행동 이벤트를 배제), 프로필 직접 기록일지(단, QT-7 "동일 이벤트 집합 → 동일 프로필" 불변식과의 정합 필요). 시드 가중치 크기·행동 신호 대비 감쇠 정책 포함 — 미기재.
- [ ] **OQ-6 · ORCID 활용**: ORCID 로그인이 라이브(#347 closed)인데, ORCID 프로필/저작에서 관심사를 유도해 시딩에 쓸지 — 동의·스코프 미기재.
- [ ] **OQ-7 · 유닛 배치**: 온보딩 UI의 unit-of-work 배치 — U10(마이페이지/계정) 확장인지 신규 유닛인지 — 미기재.

---

**요약**: FR 2건(FR-44~45 제안) · 신규 NFR 0건(기존 NFR-P4·QT-7·SEC-8 적용) · 제약 2건(C-7~8 제안) · 미해결 질문 7건. 최고 ID: FR-45 · C-8. **CONSTRUCTION 진입 전 Open Questions 전건 인간 결정 필요(승인 게이트).**
