# U11 확장 — 웹검색 레퍼런스 Functional Design (+NFR 적용)

> **상태**: 🟡 DRAFT 제안 (2026-07-23) · **SSOT 입력**: `inception/requirements/web-references.md`(RESOLVED) · `requirements.md` FR-49·C-11 · `stories.md` 에픽 14 US-WR1~2 · `unit-of-work.md` U11 확장 주석
> 본 파일은 기존 U11 설계 문서군(본 디렉터리)의 **확장분만** 기술한다 — 기존 설계 불변. U14/U15 전례를 따라 기능 설계 + NFR 적용을 단일 파일로 통합한다. **신규 유닛·신규 배포 단위·신규 API 엔드포인트 없음.**

## 1. 신규 컴포넌트 *(evidence 모듈 내)*

- **`WebReference`** *(frozen dataclass)*: `title` · `url` · `doi: str | None` · `authors: tuple[str, ...]`(표시용 상위 몇 명) · `year: int | None` · `source: 'semantic_scholar' | 'openalex'`. **표시 메타만** — 본문/초록 텍스트를 담지 않는다(C-11).
- **`ScholarlyWebSearchPort`** *(Protocol)*: `search(query: str) -> tuple[WebReference, ...]`.
- **`ScholarlyApiSearchClient`**: Semantic Scholar Graph `/paper/search` + OpenAlex `/works?search=`(둘 다 무키 — OpenAlex는 mailto polite pool) 호출 → 병합·DOI/URL dedupe → 상한 `DOCSURI_WEB_REFS_MAX`(기본 5). 항목별 `is_safe_external_url`(https·호스트) 검증 통과분만 — **프로바이더 반환값 원본만, URL 조립 금지**(무날조). 전체 타임아웃 `DOCSURI_WEB_REFS_TIMEOUT_S`(기본 4s), 실패 시 백오프 1회 후 Noop.
- **`NoopScholarlyWebSearchClient`**: 빈 튜플 반환 — 기본 배선(테스트·`DOCSURI_WEB_REFS_ENABLED=false`)이자 저하 경로(novelty `NoopExternalSearchClient` 전례).

## 2. 질의 규칙 *(카브아웃 Q9/Q25=A)*
- 질의 = 그 턴의 **corpus 검색 topic**(사용자가 이미 작성한 짧은 주제문) → `sanitize_external_query`(≤180자) 통과 후 전송. Evidence 본문·첨부·이전 턴 내용은 **전송하지 않는다**.
- `sanitize_external_query`는 현재 `novelty/security.py`의 순수 함수 — evidence→novelty 역방향 의존을 피하기 위해 **`docsuri_shared`로 승격 + `novelty.security` 재수출**(#167 authz 이전과 동일한 동일성 보존 패턴 — 기존 소비자 rewire 불요).

## 3. 오케스트레이터 통합 — 구조적 보증
- 웹 검색은 **LLM 추출 완료 후, 성공 턴에서만** 호출된다 — **웹 결과는 LLM 입력(프롬프트·추출 대상)에 절대 들어가지 않는 post-hoc 장식**이다. 이 순서가 C-2(생성 산문 금지)·환각·QT-8 평가셋 확장을 원천 차단하는 구조적 근거다(BR-WR2).
- 실패·타임아웃·0건 → `webReferences` 생략, `TurnSuccessResult` 불변(BR-WR5). abstain 턴은 v1 미동봉(계약 최소화 — abstain 시 웹 레퍼런스 제공은 추후 옵션으로 명시 유보).
- 쿼터: 기존 evidence 턴 쿼터(30/day)가 이미 턴 진입을 게이트 — 웹 검색에 추가 게이트·CostGuard 기록 없음(OQ-6 결정, 무키·무료·무LLM).

## 4. 공유계약 확장 *(FE 가시 — 유일한 계약 변경)*
- `shared/dtos/evidence.schema.json`: `EvidenceResult.webReferences?: WebReferenceRef[]` *(optional)* — `{title, url, doi?, authors?, year?, source}`. **SourceRef가 아니며** claims의 supporting/conflicting과 무관(C-11 — `web:` 네임스페이스 신설 없음). 기존 codegen으로 python `_generated`·FE 타입 재생성.
- 하위호환: optional 필드 — 기존 저장 결과·구 클라이언트 무영향.

## 5. novelty(U12) 합류 *(US-WR2)*
- `ExternalApiSearchClient`에 scholarly 소스 추가 — 동일 `ScholarlyApiSearchClient`를 호출해 기존 `RetrievalBundle` 항목 형상(title/url 등)으로 매핑, GitHub/HuggingFace/Zenodo 대열에 합류. **소스별 실패 격리 기존 계약 유지**(BR-WR6).

## 6. FE *(U13 agent chat 표면)*
- 성공 턴 결과 하단 **"웹 레퍼런스" 접이식 섹션**: 제목 링크(새 탭, `rel="noopener noreferrer"`) + 저자·연도·출처 뱃지. 이스케이프 렌더(SEC-5 — 원시 HTML 주입 금지). `webReferences` 부재/빈 배열 시 섹션 미표시.

## 7. Business Rules
- **BR-WR1** 링크백 전용(C-11): 페이지 fetch·본문 저장·재배포 없음 — `WebReference`엔 프로바이더 메타만.
- **BR-WR2** LLM 무접촉: 웹 결과는 프롬프트·추출 입력에 불포함 — claims 경로와 구조적 분리(§3 호출 순서가 보증).
- **BR-WR3** 최소 질의: `sanitize_external_query`(≤180자), 그 턴의 topic만 전송.
- **BR-WR4** 무날조: 프로바이더 반환 URL/DOI 원본만 — https·호스트 검증 실패 항목 드랍, 조립·생성 금지.
- **BR-WR5** Noop 저하: 장애·타임아웃·0건 = 조용한 생략 — 턴 성공 유지, abstain·오류 아님.
- **BR-WR6** 소스 격리(novelty): scholarly 실패가 타 외부 소스·잡 진행에 무영향.

## 8. Testable Properties
- 프로바이더 장애 주입 → 턴 성공 + `webReferences` 없음 (US-WR1 저하).
- LLM 추출 입력 캡처 → 웹 결과 문자열 미포함 (BR-WR2 구조 검증).
- http URL·URL 결측 항목 드랍, DOI 중복 dedupe 1회 (BR-WR4).
- 장문 topic → 전송 질의 ≤180자 (BR-WR3).
- novelty: scholarly 실패 시 GitHub/HF/Zenodo 결과 보존 (BR-WR6).
- 쿼터 소진 → 턴 거부 시 웹 검색 미호출 (기존 게이트 확인).
- `DOCSURI_WEB_REFS_ENABLED=false` → Noop 배선, 결과에 필드 부재.

## 9. NFR 적용 *(신규 NFR 없음 — `inception/requirements/web-references.md` NFR 절 준수)*

| 기존 NFR | 적용 |
|---|---|
| **SEC-9** | 프로바이더 원시 응답 미노출 — 표시 필드만. 로그에는 sanitize된 질의만(사용자 식별 무관). |
| **SEC-5** | FE 이스케이프 렌더(§6). |
| **NFR-C1** | 비대상 — 무키·무료·무LLM(CostGuard 기록 없음, §3). |
| **NFR-P6** | post-extraction 4s cap — 스트리밍/응답 SLA 영향 bound(타임아웃=Noop). |

- **배포/인프라**: 신규 배포 단위 없음(API 모듈 ① 내). env knobs: `DOCSURI_WEB_REFS_ENABLED`(기본 true) · `DOCSURI_WEB_REFS_MAX`(기본 5) · `DOCSURI_WEB_REFS_TIMEOUT_S`(기본 4) · `DOCSURI_OPENALEX_MAILTO`(권장 — polite pool). S2 무키 레이트리밋 유의 — 백오프 1회, 이후 Noop.

## 10. Traceability
FR-49(§1~5) · C-11(BR-WR1·§4) · US-WR1(§3·§4·§6, BR-WR2~5) · US-WR2(§5, BR-WR6) · SEC-5/9(§6·§9) · NFR-C1 비대상(§3·§9) · NFR-P6(§9) · 카브아웃 Q9/Q25(§2·BR-WR3)
