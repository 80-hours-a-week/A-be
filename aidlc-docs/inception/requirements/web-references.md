# 웹검색 레퍼런스 (Web Search References) — 요구사항 스펙

> **상태**: 🟡 DRAFT — Open Questions **오너 결정 대기** (승인 게이트; 결정 전 `requirements.md` 미등재) · **범위**: Phase 3 성장 스코프 3번 항목 · **프레이밍**: roadmap §5.3 — **evidence 에이전트의 *도구***로 구현, 독립 기능 아님
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §5.3·§1·§6 · `requirements.md` novelty 카브아웃(2026-06-29 — Q8=B 뉴스 차기 사이클·Q9/Q25=A 최소 질의) · U11 evidence 코드 현황(`backend/modules/evidence/tools.py`) · U12 novelty 외부검색 전례(`backend/modules/novelty/adapters.py`·`security.py`)
> **ID 규약**: 마스터 시리즈 연속 — 결정 후 **FR-49(안)** 등재 예정 (현재 최고 ID: FR-48 · C-10).

## 배경 — 지금 있는 것

- **U11 evidence 에이전트는 corpus 전용이다**: `EvidencePaperSearchTool`(hybrid/explicit/literal)·`EvidenceDocModelTool` 뿐 — 외부 소스 도구가 없다. 모든 출처는 `SourceRef{paperId, recordRef, anchor, quote}`로 실재성 검증되며, 비-arXiv 전례는 `userdoc:{uuid}` 네임스페이스 하나(무날조: arxiv.org URL 조립 금지).
- **U12 novelty에는 외부검색 전례가 이미 있다**: `ExternalSearchPort.search(query)` — GitHub repos·HuggingFace datasets·Zenodo(전부 키리스 공개 API), `sanitize_external_query`(≤180자 최소 질의 — Q9/Q25=A 익명화 규칙의 코드화), `is_safe_external_url`(https+호스트 검증), Noop 클라이언트 저하. **웹검색 도구는 이 패턴의 사촌이다.**
- **원 카브아웃(2026-06-29)**: "v1은 GitHub·데이터셋 외부 탐색까지만, **최신 뉴스 검색은 다음 사이클**"(Q8=B) — 그 "다음 사이클"이 지금이다. 단 roadmap §5.3은 소비 주체를 novelty가 아닌 **evidence 에이전트**로 옮겨 명시했다.
- **운영 환경**: 로컬 mac-mini 서빙 — 외부 API 키는 env로 주입(task IAM role 없음), 비용은 오너 개인 부담.

## Proposed Functional Requirement *(결정 후 등재)*

| ID | Requirement | Source | Acceptance (안) |
|---|---|---|---|
| **FR-49(안)** | **웹검색 레퍼런스 도구 [U11]**: evidence 에이전트가 턴 처리 중 웹 검색(소스 OQ-1·범위 OQ-2)을 수행해, corpus 근거를 보완하는 **웹 레퍼런스**(제목·URL 링크백)를 결과에 동봉한다. 질의는 기존 카브아웃 규칙 준수 — 사용자 원문/Evidence 전체 미전송, `sanitize_external_query` 수준 최소 질의(Q9/Q25=A). 무날조: **프로바이더가 반환한 실재 URL만** 노출, URL 조립·요약 생성 금지. | roadmap §5.3 · 카브아웃 Q8/Q9/Q25 | 웹 레퍼런스는 실제 검색 결과에 존재하는 URL만 담는다(https·호스트 검증). 프로바이더 장애·키 미설정 시 corpus-only 결과로 저하하며 turn을 실패시키지 않는다(OQ-8). 근거 참여 수준은 OQ-4 결정을 따른다. |

## 기존 NFR/제약 적용 *(신규 NFR 없음 예상)*

| 기존 ID | 적용 방식 |
|---|---|
| **SEC-9** | 내부 점수·프로바이더 원시 응답 미노출 — 표시용 필드(제목·URL·스니펫 여부는 OQ-5)만. |
| **SEC-5** | 외부 콘텐츠는 이스케이프 렌더 — 원시 HTML 주입 금지(웹 스니펫은 특히). |
| **NFR-C1** | LLM 비용 아님·외부 API 비용 — 프로바이더가 유료면 CostGuard/쿼터 편입 여부가 OQ-6. |
| **C-1/C-6** | 웹 페이지 본문 재배포 금지 — 링크백 우선(U15 BR-TN6 동형). 본문 발췌 허용 여부는 OQ-4/5. |
| **C-2/QT-8** | 생성 산문 금지·무날조 평가셋 — 웹 결과가 claims에 참여하면(OQ-4=b) 검증 확장이 필요하다. |

## Open Questions — 오너 결정 필요 ⬅ **승인 게이트**

- [ ] **OQ-1 · 검색 프로바이더**: 무엇으로 검색하나? (a) **키 기반 웹검색 API**(Brave Search·Tavily 등 — 웹 일반 커버, 키·비용 발생, env 주입) (b) **학술 특화 무키/저키 API**(Semantic Scholar·OpenAlex — citation graph가 이미 S2 사용, 학술 웹만 커버) (c) 둘 다(학술 우선 + 웹 일반 보조). *비용·ToS·로컬 env 키 관리가 결정 축.*
- [ ] **OQ-2 · 검색 범위**: 웹 일반인가, 원 카브아웃이 미뤘던 **뉴스**인가, 둘 다인가? (연구 맥락에선 프로젝트 페이지·블로그·구현체가 뉴스보다 유용할 때가 많다.)
- [ ] **OQ-3 · 소비 주체**: roadmap대로 **evidence(U11) 전용**인가, 원 카브아웃의 주체였던 novelty(U12)에도 같은 포트를 노출하나? (포트/어댑터는 공유 가능 — 노출 범위만의 문제.)
- [ ] **OQ-4 · 근거 취급** *(가장 큰 설계 갈림길)*: 웹 결과를 (a) **레퍼런스 목록으로만** — 결과에 별도 "웹 레퍼런스" 섹션, claims(지지/상충 출처)에는 불참여 → 무날조 검증 부담 없음, 스키마 추가 최소 (b) **SourceRef로 claims 참여** — `web:{...}` 네임스페이스 신설 + 페이지 본문 quote 필요 → 실재성 검증·C-2·QT-8 확장, 공유계약(`evidence_schema`, FE 가시) 변경. *(a)가 U15 링크백-only와 동형의 안전한 시작 — 권고 (a).*
- [ ] **OQ-5 · 본문 fetch**: 프로바이더 검색 결과(제목·URL·프로바이더 제공 스니펫)만 쓰나, 페이지를 직접 fetch해 발췌하나? *fetch는 SSRF 방어·robots/ToS·C-1 부담 동반 — 권고: v1은 검색 결과 메타만(fetch 없음).*
- [ ] **OQ-6 · 비용/쿼터**: 웹검색 호출을 기존 evidence 쿼터(30/day)에 흡수하나, 별도 한도를 두나? 유료 프로바이더(OQ-1=a)면 CostGuard 기록 대상인가?
- [ ] **OQ-7 · 유닛 배치**: **U11 확장**(권고 — roadmap이 "독립 기능 아님·에이전트 도구"로 명시, U14/U15와 달리 자체 표면이 없다) vs 신규 유닛.
- [ ] **OQ-8 · 실패 저하**: 프로바이더 장애·키 미설정 시 — *권고: Noop 저하(웹 레퍼런스 없이 corpus-only 결과 정상 반환, abstain 아님 — novelty NoopExternalSearchClient 전례).*

---

**요약**: 제안 FR 1건(FR-49안) · 신규 NFR 0건 예상 · 신규 제약 후보 0~1건(OQ-4/5 결정에 따라 웹 콘텐츠 경계 제약 추가 가능) · **미해결 질문 8건 — 오너 결정 대기**. 결정 후: `requirements.md` 등재 → 스토리 → unit-of-work(OQ-7) → 설계.
