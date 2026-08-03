# unit-of-work.md — 유닛 정의 (Units of Work)

**단계**: INCEPTION → Units Generation · **일자**: 2026-06-15
**근거**: `application-design/`(U1~U6), UQ1=A(6 유닛), UQ2=A(모노레포), UQ3=A(4 배포 단위), UQ4=A(데모 우선), UQ5=A(공유 계약 `shared/`). 2026-06-26 U1 Corpus 리뷰: 신규 유닛 없이 기존 U1 확장.
**2026-08-03 유닛 재구성**(`inception/plans/unit-recomposition-plan.md`, UQ1~5 답변 완료): U10·U13 정식 등재, U11/U12 코드 위치 정정, 구 `research` 모듈 U11 흡수(`backend/modules/evidence/sessions/`), `user_docmodel` U1 소유 확정(포트 `docsuri_shared.ports.UserDocModelCoordinatorPort`).

**정의**: 유닛 = 개발용 스토리 논리 묶음. 모듈형 모놀리스(DQ1)이므로 일부 유닛은 한 배포 단위(API) 내 **모듈**, 일부는 **독립 배포**(워커·프런트).

---

## 유닛 정의

| 유닛 | 책임 | 유형 | 배포 단위 | 코드 위치 | 경로 종류 |
|---|---|---|---|---|---|
| **U1 Ingestion** | arXiv·Semantic Scholar·OpenAlex AI/ML 논문 수집 → FullText → eager DocModel → DocModel Block 청크·임베딩 → 공유 Corpus 인덱스/OpenSearch·S3 생성·갱신(단일 writer) | 독립 워커 | ② 인제스천 워커 | `ingestion/` | 이벤트/스케줄 |
| **U2 Discovery** | 자연어 질의 동기 검색 읽기 경로(질의 이해·하이브리드 검색·랭킹·근거화 어댑팅·결과 조립) | API 모듈 | ① API | `backend/modules/discovery/` | 동기 REST |
| **U3 Accounts/Auth** | 가입/로그인/세션·자격증명·**객체 소유권 인가 단일 결정점** | API 모듈 | ① API | `backend/modules/accounts/` | 동기 REST(+이벤트 신호) |
| **U4 Library** | 검색 저장·라이브러리·이력(소유자 비공개) | API 모듈 | ① API | `backend/modules/library/` | 동기 CRUD(+이력 이벤트 소비) |
| **U5 Frontend** | SSR 폰 우선 웹 UI(검색·결과·계정·라이브러리·상태; 폰 목업 프레임) | 독립 프런트 | ④ 프런트엔드 | `frontend/` | 동기 REST(클라이언트) |
| **U6 Reliability/Ops** | DQ5 횡단 미들웨어/게이트웨이(API 내) + 운영 워커(탐지·대시보드) | 미들웨어 + 워커 | ① API(게이트웨이) · ③ Ops 워커(탐지·대시보드) | `backend/middleware/` · `ops/` | 동기 게이트 + 이벤트 백본 |
| **U7 Summarization** *(2026-06-18 편입)* | 검색된 단일 논문의 온디맨드 요약(Sonnet)·초록 번역(Haiku)·개인화(persona/뷰/용어집); 근거 앵커·기권; 영구저장(S3)+핫캐시(Redis) | API 모듈(+초장문 비동기 잡 옵션) | ① API (+③ 비동기 잡 옵션) | `backend/modules/summarization/` | 동기 REST(스트리밍) + 이벤트(관측/비용) |
| **U8 Citation Graph** *(2026-06-19 편입)* | 논문 상세보기의 backward references 각주 트리; ID 해소·unresolved 분리·깊이/노드 상한·라이브러리 저장 연동; 외부 citation API 캐시/저하 | API 모듈 | ① API | `backend/modules/citation_graph/` | 동기 REST + 캐시 + 관측 이벤트 |
| **U9 Personalization** *(2026-06-23 편입)* | 의미 있는 사용자 행동 이벤트 기록, 관심 프로필 집계, 개인화 설정/삭제/초기화, 검색·요약·번역 기본값 개인화 제공 | API 모듈 | ① API | `backend/modules/personalization/` | 동기 REST + 비차단 이벤트 기록 |
| **U10 MyPage** *(2026-08-03 등재 — 타 팀원 빌드 머지분 사후 반영)* | 마이페이지 — mock 구독(플랜 표시·"하는 척만" Q10, 실 PG/청구 없음 — U16 편입 후 플랜 값은 U16 소유) + 계정 메뉴 백엔드(`/mypage/*`). 관심 논문·로그아웃 메뉴는 FE가 U4 `GET /library`·U3 `POST /logout` 직접 호출(U10 백엔드 없음) | API 모듈 + FE 메뉴 | ① API (+④ 프런트엔드) | `backend/modules/mypage/` | 동기 REST |
| **U11 Evidence Agent** *(2026-06-29 편입 — 재인셉션 Phase 4 / requirements 초안 "[U4]" 오기 → U11 정정 2026-06-30)* | 로그인 필수 대화형 다논문 문헌탐색·근거형성 Agent. 사용자 질의/첨부에 대해 여러 논문을 교차확인해 핵심 주장·방법·결과 수치·한계를 추출·비교하고 쟁점 오버레이로 제시; 근거 없으면 기권(FR-5). 세션·결과 owner-scoped 영속. EvidenceFormationPort(D5)를 통해 U12(novelty Agent)에 Tool로 노출. **2026-07-23 확장**: 웹검색 레퍼런스 도구(FR-49 — 학술 공개 API 링크백 전용, C-11; 포트는 U12에도 노출) | API 모듈 (+비동기 잡 옵션) | ① API (+③ 잡 옵션) | `backend/modules/evidence/` *(2026-08-03 재구성 정정 — 구 표기 `evidence_agent/`는 오기)* + 세션 셸 `backend/modules/evidence/sessions/` *(구 `research` 모듈 흡수 — 라우트 `/api/research`·readyz 라벨 `research` 유지)* | 동기 REST(SSE 스트리밍) + 비동기 잡 (장분석) |
| **U12 Novelty Agent** *(2026-06-29 편입 / 번호 확정 2026-06-30 — requirements 초안 "[신규]")* | 차별화(novelty)/연구아이디어 형성 Agent. 자연어 의도·업로드 원고에서 EvidenceFormationPort(U11)·U2 `full` 검색·GitHub/데이터셋 외부 탐색을 소비해 유사 연구 정리·bounded 차별화 아이디어·실험 계획·원고 위험 신호 생성; 단계별 진행상태·owner-scoped 저장·승인형 Notion export; 근거 없으면 기권(FR-5). FR-30~35·US-NV1~9·QT-10·NFR-P5/R3 | 독립 Agent 워커 (+비동기 잡) | ⑤ novelty 워커 (`Docsuri-Novelty` 스택, `NOVELTY_AGENT_ENABLED` 게이트) | `backend/modules/novelty/` + `Docsuri-Novelty` 워커 스택(`ops/cdk/stacks/`) *(2026-08-03 재구성 정정 — 설계 문서는 `construction/novelty-agent/`)* | 비동기 잡(생성/폴링/취소) |
| **U13 Agent Chat Frontend** *(2026-08-03 등재 — 인셉션 산출물[requirements·stories US-AG1~6·application-design·construction/agent-chat-frontend]은 U13으로 완결·Build&Test 완료였으나 본 표 등재 누락 정정)* | 에이전트 채팅 UI — evidence/novelty 모드 선택·고정(BR-AG-1), 세션 drawer·멀티턴, 탐구 timeline, 첨부(PDF/MD/TXT allowlist), mock/real transport 경계·failed/degraded 분류. U11(`/api/research`)·U12(novelty 잡) REST/SSE 소비 | 프런트 슬라이스 | ④ 프런트엔드 | `frontend/`(agent chat 컴포넌트·transport) | 동기 REST(클라이언트) + SSE |
| **U14 Onboarding** *(2026-07-23 편입 — Phase 3)* | 가입/차기 로그인 시 관심사 수집(arXiv 카테고리 픽커, 스킵 가능) + ORCID 프로필·저작 관심사 유도 → **관심사 설정 행동 이벤트**(FR-39 개정)로 U9 프로필 시딩(`categoryWeights`+`keywordWeights`) — 개인화 콜드스타트 해소. US-P5 선행 포함. FR-44~46·US-OB1~4·C-7/C-8 | API 모듈 + FE 플로우 | ① API (+④ 프런트엔드) | `backend/modules/onboarding/` *(제안 — 설계 단계 확정)* · `frontend/`(픽커 플로우) | 동기 REST + 비차단 이벤트 기록 |
| **U15 Trends/Notifications** *(2026-07-23 편입 — Phase 3)* | 명시적 팔로우 주제 목록(설정 UI, U14/U9 관심 프로필과 별개) + **옵트인** 이메일 다이제스트 — harvest 신규 논문을 키워드/임베딩 유사도로 매칭해 plain list 발송(기본 daily·사용자 설정, 기존 `EMAIL_PROVIDER` 경로 = SES on `559352512800`). FR-47~48·US-TN1~3·C-9/C-10 | API 모듈 + 배치 발송 잡 + FE 설정 플로우 | ① API (+③ 잡) (+④ 프런트엔드) | `backend/modules/trends/` *(제안 — 설계 단계 확정)* · `frontend/`(설정 플로우) | 동기 REST + 스케줄 배치 발송 |
| **U16 Subscription/Plans** *(2026-07-24 편입 — Phase 3)* | 플랜/티어 도메인(2단 **free/plus**) — 플랜이 에이전트 daily 쿼터(evidence·novelty)를 결정, 기타 기능 전 티어 동일. **v1 결제 카브아웃**(C-12): ADMIN 수동 부여(월 기간)·paid-through-period·만료 자동 free 전환. per-user 일일 spend 롤업 신설(실측 캘리브레이션 파이프라인). FR-50~51·US-SB1~3·C-12 | API 모듈 + 만료 전환 잡 + FE 플랜 표시 | ① API (+③ 잡) (+④ 프런트엔드) | `backend/modules/plans/` *(제안 — 설계 단계 확정)* · `frontend/`(플랜 표시) | 동기 REST + 만료 배치 |
> **U6 분할 주석**: U6는 두 곳에 산다 — (a) **게이트웨이 미들웨어**(authn/authz·검증·레이트리밋·비용 상태·근거화 강제 후크)는 API 배포 단위 ① 내부, (b) **Ops 워커**(AI 인시던트 탐지기·대시보드)는 이벤트 백본 소비 독립 워커 ③.

> **U7 주석 (요약/번역)**: U7은 결과 카드의 **온디맨드 보조 기능**(검색 SLA NFR-P1 비대상, NFR-P2). U6 게이트웨이를 단일 진입으로 도달하며, **U1 DocModel/FullText(S3 read = capability)·U6 근거화 후크/비용 게이트(`shared/ports` lib)에 의존**한다(U2와 동일 패턴 — 코드 순환 없음). LLM 호출은 U2 검색과 별개 경로. 대부분 단일 콜 동기 스트리밍, **초장문(map-reduce)만 비동기 잡**(배포 ③). 산출물은 S3 영구 + Redis 핫캐시(키 immutable, 논문당 평생 1회 생성).

> **U8 주석 (인용 그래프/각주 트리)**: U8은 논문 상세보기 페이지에서 호출되는 **로그인 필수 온디맨드 읽기 경로**다. v1은 backward references만 다루며 forward citations·3-hop 이상·FE 구현은 제외한다. 외부 citation API(Semantic Scholar 우선)는 온디맨드 조회 + 7일 snapshot 캐시로 감싼다. 노드 저장은 U4 Library 계약을 재사용한다.

> **U9 주석 (개인화/행동 인텔리전스)**: U9는 사용자별 원시 행동 이벤트와 집계 관심 프로필을 소유한다. v1은 검색 결과의 작은 boost/rerank와 요약/번역 기본값 제안만 다루며, 별도 추천 목록·전체 클릭스트림·hover/scroll 추적·강한 리랭크·실시간 ML 추천 파이프라인은 제외한다. U9 실패는 U2/U4/U7 본 기능을 막지 않는 비차단 저하로 처리한다.

> **U10 주석 (마이페이지)**: 2026-08-03 재구성에서 머지된 코드 기준으로 정식 등재(구 자리 주석 해소). U10은 **UI+얇은 백엔드**만 소유 — 계정 도메인 규칙은 U3, 라이브러리 데이터는 U4, 플랜/쿼터 값은 U16이 소유한다(U10 구독 표시는 mock).
>
> **U11 주석 (문헌탐색·근거형성 Agent)**: U11 = 재인셉션 차터 페이즈 4(requirements "[U4]"). LLM Agent가 Search·DocModel·Summary 도구를 자율 오케스트레이션해 다논문 근거를 형성한다. 스트리밍 우선(NFR-P6), 긴 분석은 비동기 잡 옵션(U7 패턴 재사용). EvidenceFormationPort 단일 구현자(D5 계약 게이트) — U12(연구아이디어 Agent, 미래)가 소비. U11 실패는 본 유닛 응답만 영향(U2/U4/U7/U9 비차단).
> **U11 확장 (2026-07-23 — 웹검색 레퍼런스, FR-49/C-11, 에픽 14 US-WR1~2)**: 학술 공개 API(Semantic Scholar·OpenAlex — 무키) 웹검색 도구 추가 — 결과에 **링크백 전용** 웹 레퍼런스 목록 동봉(claims 불참여, C-11 — SourceRef 실재성 검증 체계 무변경). 외부검색 포트는 U12 novelty에도 노출(GitHub/HF/Zenodo 대열 합류). Noop 저하·기존 evidence 쿼터(30/day) 흡수. **신규 유닛·신규 배포 단위 없음.** 결정 기록: `requirements/web-references.md`.
>
> **연구 에이전트 번호 재부여 완료(2026-06-29 / U12 빌드 반영 2026-06-30)**: 구 통합 "U11 Research Agent"는 폐기되고 **U11(문헌탐색·근거형성) / U12(차별화·연구아이디어 novelty)**로 분리 확정(재인셉션 차터 §4). 둘 다 본 표에 정의. **U12(novelty)는 별도 인셉션 사이클로 이미 빌드됨** — 요구사항 FR-30~35·스토리 US-NV1~9·QT-10·NFR-P5/R3, 설계/코드 `construction/novelty-agent/`, 배포 `Docsuri-Novelty` 스택(`NOVELTY_AGENT_ENABLED`). (코드/CDK는 구 U11 엄브렐러 네이밍 잔존 — 인셉션 유닛 번호는 U12.)
>
> **U14 주석 (온보딩)**: U14는 시딩 이벤트의 **생산자**일 뿐, 프로필 저장·집계는 U9 소유를 유지한다(직접 프로필 기록 금지 — C-7, TTL/재집계 소실 방지). 픽커/ORCID 유도 실패는 가입·로그인을 막지 않는 비차단 저하(NFR-P4). 결정 기록: `inception/requirements/onboarding.md`(OQ 7건 오너 결정, 2026-07-23).
>
> **U15 주석 (트렌드/알림)**: 다이제스트 실효는 **daily harvest 재개**(오너 추후 결정 — 현재 CDK `ArxivDailySchedule` `enabled=False`)에 종속 — U15 빌드/테스트는 기존 코퍼스로 가능. 매칭은 기존 코퍼스 임베딩 재사용, 팔로우 주제는 등록 시 1회 임베딩. 옵트인 전 무발송(FR-48), 발송 실패는 타 사용자·타 기능 무영향 비차단 저하. **SES sandbox→production access**(계정 `559352512800`)와 로컬 서빙용 자격증명 방식은 운영/설계 후속. 결정 기록: `inception/requirements/trends-notifications.md`(OQ 8건 오너 결정, 2026-07-23).
> **U16 주석 (구독제/플랜)**: **v1 결제 없음**(C-12 — PG 연동·청구 코드 제외, ADMIN 수동 부여만; 결제 도입 시 PG 어댑터 추가 경로). 플랜은 CostGuard 집행에 **쿼터 값만 공급**(계약 불변, NFR-C1 — 미부여=free=현행 쿼터 무회귀). **plus 수치 TBD** — `reports/costguard-spend-report-2026-07.md`(OQ-5 선행물)의 상한 산식으로 설계 단계 오너 확정(기본 제안 3×: evidence 90/day·novelty 15/day, 월 최악 ~$378/인). per-user 일일 spend 롤업 신설로 차기 캘리브레이션은 실측 기반. 결정 기록: `inception/requirements/subscription.md`(OQ 8건 오너 결정, 2026-07-24).

## 배포 단위 (UQ3=A)
1. **API 서비스** — U2 + U3 + U4 + **U7 + U8 + U9 + U10 + U11(+sessions) + U14 + U15 + U16** + U6 게이트웨이 미들웨어 (동기 REST, 모듈형 모놀리스) *(2026-08-03 재구성: U10·U14~U16 반영, U11 세션 셸 포함)*
2. **인제스천 워커** — U1 (이벤트/스케줄)
3. **Ops/탐지 워커** — U6 탐지기·대시보드 (이벤트 백본) **(+ U7 초장문 요약 비동기 잡 옵션)**
4. **프런트엔드** — U5 (SSR) + **U13 agent chat 슬라이스** (+U14/U15/U16 FE 플로우)
5. **novelty 에이전트 워커** — U12 (`Docsuri-Novelty` 스택, `NOVELTY_AGENT_ENABLED` 게이트, 비동기 잡 — 별도 인셉션 사이클로 빌드; 코드 위치 `backend/modules/novelty/`)

공유 capability(기술 미확정): Corpus/OpenSearch 인덱스, DocModel/FullText 오브젝트 스토리지, GROBID 런타임, 관리형 DB/영속화, 이벤트 버스/백본, 임베딩/LLM 게이트웨이, DLQ. **(U7 추가 활용: 오브젝트 스토리지[DocModel/FullText read + 요약 영구저장]·핫캐시[Redis]·LLM 게이트웨이[Sonnet/Haiku]. U8 추가 활용: citation snapshot 캐시/스토어·외부 citation API 쿼터 카운터. U9 추가 활용: 사용자 행동 이벤트/관심 프로필 RDS 테이블.)**

## 코드 조직 전략 (Greenfield, UQ2=A 모노레포)
```text
<repo-root>/
├── frontend/                # U5 — SSR 폰 우선 웹 (배포 ④)
├── backend/                 # 배포 ① API (모듈형 모놀리스)
│   ├── modules/
│   │   ├── discovery/       # U2
│   │   ├── accounts/        # U3
│   │   ├── library/         # U4
│   │   ├── summarization/   # U7 — 요약/번역(온디맨드, Sonnet/Haiku)
│   │   ├── citation_graph/  # U8 — 각주 트리/backward references
│   │   ├── personalization/ # U9 — 행동 이벤트/관심 프로필/개인화 설정
│   │   ├── mypage/          # U10 — 마이페이지(mock 구독·계정 메뉴)
│   │   ├── evidence/        # U11 — 근거형성 Agent (+ sessions/ 채팅 세션 셸, 구 research)
│   │   ├── novelty/         # U12 — novelty Agent (워커 스택 Docsuri-Novelty)
│   │   ├── onboarding/      # U14 — 온보딩(관심사 시딩 이벤트 생산)
│   │   ├── trends/          # U15 — 트렌드/알림(팔로우 주제·다이제스트)
│   │   ├── plans/           # U16 — 구독제/플랜(쿼터 값 공급)
│   │   └── user_docmodel/   # U1 백엔드 seam — 사용자 PDF→DocModel 코디네이터(포트=docsuri_shared.ports)
│   └── middleware/          # U6 게이트웨이(authn/authz·검증·레이트리밋·비용·근거화 후크)
├── ingestion/               # U1 — 인제스천 워커 (배포 ②)
├── ops/                     # U6 — 탐지기·대시보드 워커 (배포 ③)
└── shared/                  # UQ5=A 공유 계약 단일 소유
    ├── vector-spec          # 임베딩 스키마(U1 writer ↔ U2 reader 동일 공간 불변식)
    ├── dtos                 # 결과/카드/계정/라이브러리 DTO
    ├── events               # 이벤트 스키마(SearchExecuted, AI 인시던트)
    └── ports                # 횡단 후크 인터페이스(근거화·비용) — 의존성 역전(코드 순환 방지)
```
구체 언어·프레임워크·런타임은 **NFR Requirements/Construction**에서 확정(이전 사이클 Python 백엔드 + Next.js 프런트는 선행 사례).

## 빌드/개발 순서 (병렬화 조율 반영 - 2026-06-16)
개발 기간 단축을 위해 `shared/` 공용 규약을 선행 작성한 뒤, 아래와 같이 3개 독립 트랙으로 병렬 개발을 진행합니다.

* **준비 단계**: `shared/` 규약 고정 (`vector-spec` 및 API DTO, 이벤트 스펙 선행 작성)
* **[트랙 1] 데이터 파이프라인**: **U1 Ingestion** (멀티소스 Corpus 인제스천 워커) ──> **U6 Reliability/Ops** (비동기 탐지 워커)
* **[트랙 2] 인증 및 사용자 데이터**: **U3 Accounts** (가입/로그인) ──> **U4 Library** (저장/라이브러리)
* **[트랙 3] 사용자 검색 및 UI**: **U2 Discovery** (Mock API 기반 선행 개발) ──> **U5 Frontend** (UI 화면 및 인터랙션)
* **[확장 / 2026-06-18] 요약·번역**: **U7 Summarization** — 코어(U1~U6) 빌드·배포 완료 후 편입되는 신규 유닛. **선행 의존**: U1(DocModel/FullText S3 capability)·U6(근거화 후크·CostGuard)·shared(DTO·ports) = 이미 가용. 결과 카드 표면은 U2/U5와 연결. 단일 트랙으로 CONSTRUCTION 유닛 루프 진행(**실배포 기준 real-first 구현** — LLM·스토어 어댑터는 포트 뒤 실 구현 단일본[Bedrock·S3·Redis], mock/인메모리 대역 없음. _2026-06-18 U7 FD 답변 Q10/Q11로 확정._).
* **[확장 / 2026-06-19] 인용 그래프·각주 트리**: **U8 Citation Graph** — 논문 상세보기 페이지의 4개 액션 중 각주 트리 API를 제공한다. **선행 의존**: U3/U6(로그인·게이트웨이), U4(라이브러리 저장 계약), U5/상세보기 분기(FE 표면), shared(DTO·events). Requirements/User Stories/Units Generation까지만 진행하고, Construction은 별도 승인 후 시작한다.
* **[확장 / 2026-06-23] 개인화/행동 인텔리전스**: **U9 Personalization** — 행동 이벤트와 관심 프로필을 소유하는 API 모듈. **선행 의존**: U3/U6(로그인·게이트웨이), U2(검색 결과 개인화), U4(라이브러리 신호), U7(요약/번역 기본값), U5(설정/표시), shared(DTO·events). Construction은 U9 단일 유닛 루프로 진행한다.
* **[확장 / 2026-06-24 → 2026-06-28 재구성] 연구 에이전트**: 구 통합 "U11 Research Agent"는 폐기되고 **문헌탐색·근거형성 / 연구아이디어 2개 유닛으로 분리**(재인셉션 차터 §4). 유닛 번호·경계·선행 의존(2유닛 간 의존 포함)은 **신규 인셉션 사이클의 units-generation에서 재부여**한다.

> 각 유닛은 CONSTRUCTION의 유닛별 루프(Functional/NFR/Infra Design → Code Generation)로 진행한다.
