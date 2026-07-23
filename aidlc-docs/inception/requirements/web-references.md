# 웹검색 레퍼런스 (Web Search References) — 요구사항 스펙

> **상태**: 🟢 RESOLVED — Open Questions **전건 결정(2026-07-23, 오너)** → 승인 게이트 통과, `requirements.md` **등재 완료**(FR-49·C-11) · **범위**: Phase 3 성장 스코프 3번 항목 · **유닛**: **U11 확장**(신규 유닛 없음 — OQ-7 결정), 외부검색 포트는 U12 novelty에도 노출(OQ-3)
> **출처(SSOT 입력)**: `reports/roadmap-2026-07.md` §5.3·§1·§6 · `requirements.md` novelty 카브아웃(2026-06-29 — Q8=B·Q9/Q25=A) · U11 evidence 코드 현황(`backend/modules/evidence/tools.py`) · U12 novelty 외부검색 전례(`backend/modules/novelty/adapters.py`·`security.py`) · 본 문서 §결정 기록 오너 답변(2026-07-23)
> **ID 규약**: 마스터 시리즈 연속 — FR-49·C-11. 등재분이 SSOT이며 본 문서는 결정 경위를 보존한다.

## 배경 — 결정 시점의 현황

- **U11 evidence 에이전트는 corpus 전용이었다**: `EvidencePaperSearchTool`(hybrid/explicit/literal)·`EvidenceDocModelTool` 뿐. 모든 출처는 `SourceRef{paperId, recordRef, anchor, quote}`로 실재성 검증되며, 비-arXiv 전례는 `userdoc:{uuid}` 네임스페이스 하나(무날조: arxiv.org URL 조립 금지).
- **U12 novelty에는 외부검색 전례가 이미 있다**: `ExternalSearchPort.search(query)` — GitHub repos·HuggingFace datasets·Zenodo(전부 키리스 공개 API), `sanitize_external_query`(≤180자 최소 질의 — Q9/Q25=A 규칙의 코드화), `is_safe_external_url`(https+호스트 검증), Noop 클라이언트 저하. 웹검색 도구는 이 패턴의 사촌이다.
- **원 카브아웃(2026-06-29)**: "최신 뉴스 검색은 다음 사이클"(Q8=B) — 이번 사이클이 그 재진입이며, roadmap §5.3이 소비 주체를 evidence 에이전트로 명시했다(OQ-3 결정으로 novelty에도 포트 노출).
- **운영 환경**: 로컬 mac-mini 서빙 — 무키 프로바이더 선택(OQ-1=b)으로 키 관리·외부 API 비용이 발생하지 않는다.

## Functional Requirements

| ID | Requirement | Source | Acceptance |
|---|---|---|---|
| **FR-49** | **웹검색 레퍼런스 도구 [U11/U12]**: evidence 에이전트(U11)가 턴 처리 중 **학술 공개 API**(Semantic Scholar·OpenAlex — 무키, OQ-1)로 외부 검색을 수행해, corpus 근거를 보완하는 **웹 레퍼런스 목록**(제목·실재 URL 링크백 — claims 불참여, OQ-4·C-11)을 결과에 동봉한다. 같은 외부검색 포트는 novelty(U12)에도 노출한다(OQ-3). 질의는 최소 질의 규칙(Q9/Q25=A) 준수, 페이지 본문 fetch 없음(OQ-5), 호출은 기존 evidence 쿼터(30/day)에 흡수(OQ-6). | roadmap §5.3 · OQ-1~6/8 결정 | 웹 레퍼런스는 프로바이더가 반환한 실재 URL/DOI만(무날조 — URL 조립·요약 생성 금지, https·호스트 검증). claims의 supporting/conflicting에 웹 출처 불참여 — SourceRef 실재성 검증 체계는 corpus/userdoc 전용 유지. 프로바이더 장애·미설정 시 Noop 저하(웹 레퍼런스 없이 corpus-only 정상 결과, abstain 아님 — OQ-8). 공유계약 확장은 링크백 표시 필드만. |

## 기존 NFR/제약 적용 *(신규 NFR 없음)*

| 기존 ID | 적용 방식 |
|---|---|
| **SEC-9** | 내부 점수·프로바이더 원시 응답 미노출 — 표시용 필드(제목·URL/DOI·저자·연도·프로바이더 스니펫)만. |
| **SEC-5** | 외부 콘텐츠 이스케이프 렌더 — 원시 HTML 주입 금지. |
| **NFR-C1** | LLM 비용 아님·프로바이더 무키/무료(OQ-1=b) → CostGuard 기록 비대상, 호출량은 evidence 쿼터 30/day에 흡수(OQ-6). |
| **C-1/C-6** | 웹 페이지 본문 재배포 없음 — 링크백 전용(C-11, U15 BR-TN6 동형). |
| **C-2/QT-8** | 웹 결과는 claims 불참여(OQ-4=a) → 무날조 검증 체계 확장 불필요, 기존 평가셋 무영향. |

## Constraints

| ID | Kind | Constraint | Source |
|---|---|---|---|
| **C-11** | technical | 웹 레퍼런스는 **링크백 전용** — 페이지 본문 fetch·저장·재배포 금지, 프로바이더 검색 결과 메타(제목·URL/DOI·저자·연도 등)만 사용·표시. 근거(claims) 참여 금지. | OQ-4/5 결정 |

## 결정 기록 (Open Questions — 전건 RESOLVED 2026-07-23)

- [x] **OQ-1 · 검색 프로바이더** → **(b) 학술 특화 무키 API** — Semantic Scholar·OpenAlex (citation graph의 S2 사용 전례, 키·비용 없음).
- [x] **OQ-2 · 검색 범위** → **일반 웹** — 뉴스 버티컬 아님. *해석 노트: OQ-1=(b)와 결합하면 실제 도달 범위는 프로바이더 커버리지(학술 웹 — 논문·프리프린트·프로시딩의 외부 URL/DOI)로 한정된다. 일반 웹 크롤 검색이 필요해지면 OQ-1 재방문(프로바이더 추가)이지 스키마 변경이 아니다.*
- [x] **OQ-3 · 소비 주체** → **U11 + U12** — 외부검색 포트를 novelty에도 노출(포트/어댑터 공유, 소비 지점만 둘).
- [x] **OQ-4 · 근거 취급** → **(a) 레퍼런스 목록 전용** — 별도 웹 레퍼런스 섹션, claims 불참여. `web:` SourceRef 네임스페이스 신설 없음.
- [x] **OQ-5 · 본문 fetch** → **프로바이더 검색 결과 메타만** — 페이지 fetch 없음(SSRF·robots/ToS·C-1 부담 회피).
- [x] **OQ-6 · 비용/쿼터** → **기존 evidence 쿼터(30/day)에 흡수** — 별도 한도·CostGuard 기록 없음(무키 프로바이더라 외부 비용 0).
- [x] **OQ-7 · 유닛 배치** → **U11 확장** — 신규 유닛 없음(자체 표면 없는 에이전트 도구).
- [x] **OQ-8 · 실패 저하** → **Noop 저하** — 프로바이더 장애·미설정 시 웹 레퍼런스 없이 corpus-only 정상 결과(abstain 아님, novelty NoopExternalSearchClient 전례).

---

**요약**: FR 1건(FR-49 등재) · 신규 NFR 0건 · 제약 1건(C-11 등재) · 미해결 질문 **0건**(8건 전건 결정) · 신규 유닛 0건(U11 확장). 최고 ID: FR-49 · C-11. **다음 단계: U11 확장 사용자 스토리 → unit-of-work 주석 → 설계.**
