# 유닛 재구성 계획 (Unit Recomposition Plan)

**작성일**: 2026-08-03 · **상태**: ✅ Part 2 적용 완료 — **UQ1=A(research→U11 흡수) · UQ2=A(user_docmodel U1 소유+포트) · UQ3=A(U8 현상 유지) · UQ4=A(사실 정정+U10/U13 등재 일괄) · UQ5=A(문서 위생)**, 적용 범위 = 레지스트리+코드 브랜치(`refactor/unit-recomposition`) · **트리거**: 사용자 지시 "유닛 재구성 — 일부 유닛이 부분적이거나 임시 방편(quick fix)"
**추가 감사 노트(develop 팁 재검증)**: 본 계획 §1의 감사는 U14~U16 편입(2026-07-23/24) 이전 HEAD 기준으로 시작했으나 develop 팁에서 재검증 완료 — D1~D5·R1~R4 전부 유효, U14~U16은 레지스트리 등재 완료 상태(단 배포 단위 표·aidlc-state.md 미반영은 본 재구성에서 정정/기록).
**대상**: `inception/application-design/unit-of-work.md` · `unit-of-work-dependency.md` · `unit-of-work-story-map.md` (유닛 레지스트리 3종) + 후속 코드 재배치(승인 범위에 따라)
**방법론**: Units Generation 재진입 — 신규 인셉션이 아니라 **레지스트리↔코드 정합 회복 + 임시 방편 유닛의 정식 편입/흡수**.

---

## §1 감사 결과 — 레지스트리 ↔ 코드 드리프트 (사실 관계, 결정 불요)

라이브 앱(`backend/wiring.py`)은 11개 모듈을 마운트한다: accounts, library, discovery, **mypage**, ops, citation_graph, personalization, **research**, novelty, summarization, evidence. 유닛 레지스트리와 대조한 결과:

| # | 항목 | 레지스트리 표기 | 실제 | 심각도 |
|---|---|---|---|---|
| D1 | U11 코드 위치 | `backend/modules/evidence_agent/` | `backend/modules/evidence/` (+ 세션 셸은 `research/`에 분산 — §2 R1) | High(오표기) |
| D2 | U12 코드 위치 | `construction/novelty-agent/` (**문서 경로**) | `backend/modules/novelty/` + `Docsuri-Novelty` 워커 스택(`ops/cdk/stacks/`) | High(오표기) |
| D3 | U10 마이페이지 | 자리 주석만("커밋/푸시 전 — 본 문서 미반영") | `backend/modules/mypage/` 머지·마운트 완료(`/mypage/*`, mock 구독 Q10). story-map엔 U10 참조 4건 존재 | High(등재 누락) |
| D4 | U13 Agent Chat Frontend | 레지스트리 3종 모두 **0건** | requirements·stories·application-design·`construction/agent-chat-frontend/`(FD·NFR·code)까지 전 인셉션 산출물이 U13 자칭·Build&Test 완료 | High(등재 누락) |
| D5 | 배포 단위/빌드 순서 | ① API = U2+U3+U4+U7+U8+U9+U11 | 실제 ① API에 U10 mypage·research 세션 셸 포함; ④ 프런트에 U13 슬라이스 포함 | Medium |

D1~D5는 결정이 필요 없는 **사실 정정**이다(단, D1의 최종 문구는 §3 UQ1 답에 따라 달라짐).

## §2 부분/임시 방편 유닛 분류 (결정 필요)

- **R1 `backend/modules/research/` (1,239줄, 5파일)** — "separated research and novelty chat session APIs"(`abe8a40`)로 급조된 **채팅 세션 셸**. 이후 evidence orchestrator에 연결(`56fc5c7`)·쿼터 우회 수정(`7898379`) 등 패치가 누적됐다. U11 유닛 정의가 이미 "세션·결과 owner-scoped 영속"을 소유한다고 명시하므로 **책임 중복**. `RESEARCH_AGENT_ENABLED` 게이트 별도 존재.
- **R2 `backend/modules/user_docmodel.py` (340줄 단일 파일)** — 사용자 PDF→DocModel 동결 계약(PR0: `userdoc:{uuid}`·`upload:{ownerId}:{jobId}:{attachmentId}`)의 코디네이터. evidence·research·novelty 3개 유닛이 소비하는 **교차 유닛 능력**이 모듈 루트에 무소속 파일로 방치. DocModel 능력 소유자는 U1이고, 리포 관례는 "포트=`shared/ports`, 구현=소유 유닛".
- **R3 `backend/modules/citation_graph/` (U8)** — controller.py 단일 파일 412줄(서비스/리포지토리 분리 없음). Build&Test 기록상 기능은 완결이나, 타 유닛 대비 구조가 얇다. 유닛 구성 문제라기보다 구조 부채.
- **R4 문서 위생** — `construction/u6-integration-proposal.md`는 2026-06-18 크리티컬 패스 ④로 이미 적용 완료된 stale 제안서(헤더는 여전히 "미적용"). `aidlc-state.md`는 2026-07-02 이후 약 1개월분 증분(v3 재임베드 컷오버, novelty 쿼리확장 개편, U9 US-P4 go-live v1.15.0 등)이 미기록 — audit.md에만 흔적 존재.

## §3 재구성 질문 (UQ — 답변 후 Part 2 적용)

**UQ1. `research` 모듈 처리** *(R1)*
- **A (권장)**: **U11로 흡수** — `research/`를 U11 evidence의 세션 서브패키지로 재배치(또는 최소한 레지스트리에서 U11 소유로 등재하고 코드 이동은 후속 브랜치). 근거: U11 정의가 이미 세션 영속을 소유; 에이전트 채팅 세션의 단일 소유자 확립; `RESEARCH_AGENT_ENABLED`→U11 게이트로 통합.
- B: 신규 유닛으로 정식 등재(예: U14 Research Chat Sessions) — 셸을 독립 유닛으로 승격.
- C: 코드 현상 유지 + 레지스트리에 "U11 소유, 별도 모듈" 주석만.

**UQ2. `user_docmodel.py` 소유/배치** *(R2)*
- **A (권장)**: **U1 소유 확정** — 포트를 `shared/ports`로 승격하고 구현은 U1 소유의 정식 모듈(`backend/modules/user_docmodel/`)로 승격. 근거: DocModel 능력 소유자=U1, 소비자 3유닛은 포트만 의존(리포 관례 `U11↔U6 shared/ports` 패턴).
- B: `shared/` 라이브러리로 통째 이동(구현 포함) — 계약+구현 동거를 허용.
- C: 현 위치 유지 + 레지스트리 주석만(부채 기록).

**UQ3. U8 구조 부채** *(R3)*
- **A (권장)**: 소형 유닛으로 현상 유지, 레지스트리에 구조 부채 주석(YAGNI — 요구 변화 시 분리).
- B: 표준 레이아웃(service/repository 분리)으로 재구성 브랜치 진행.

**UQ4. 사실 정정 + U10/U13 정식 등재 일괄 적용** *(D1~D5)*
- **A (권장)**: 본 계획 승인과 동시에 레지스트리 3종 갱신 — U10 행 신설(머지된 코드 기준: mock 구독 + 계정 메뉴, 관심논문/로그아웃은 U4/U3 직접 호출로 U10 백엔드 없음), U13 행 신설(배포 단위 ④ 프런트 슬라이스), U11/U12 코드 위치 정정, 배포 단위·빌드 순서 표 갱신, stale 주석(U10 자리 주석 등) 제거.
- B: 사실 정정만 먼저, U10/U13 등재는 별도 게이트.

**UQ5. 문서 위생 후속** *(R4)*
- **A (권장)**: `u6-integration-proposal.md` 헤더에 "적용 완료(2026-06-18) — 이력 보존" 스탬프; `aidlc-state.md`에 2026-07 증분 요약 1절 추가(별도 커밋).
- B: 이번 범위 제외.

## §4 Part 2 산출물 (승인 후)

1. `unit-of-work.md` — U10·U13 행 신설, U11/U12 정정, 배포 단위 표+④ 슬라이스 주석, 빌드 순서 갱신, UQ1/UQ2 결과 반영.
2. `unit-of-work-dependency.md` — U10(→U3 세션·U4 링크)·U13(→U11/U12 transport) 행/열 추가, research 흡수 반영, 비순환 DAG 재검증.
3. `unit-of-work-story-map.md` — U10 참조 정합화, U13 스토리(US-AG/EV/NV 프런트 계열) Owner 매핑 재검증.
4. (UQ1=A 시) 코드 재배치 브랜치 `refactor/unit-recomposition` — research→evidence 세션 서브패키지, wiring/테스트/CI 레인 추적.
5. (UQ2=A 시) user_docmodel 포트 승격 + 모듈화 브랜치(4와 동일 브랜치 가능).
6. `aidlc-state.md` 상태 항목 추가 + (UQ5=A 시) 증분 요약.

**리뷰 게이트**: UQ1~UQ5 답변 대기.
