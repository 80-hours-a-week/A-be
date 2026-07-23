# U15 Trends/Notifications — Functional Design

> **상태**: 🟡 DRAFT 제안 (2026-07-23) · **SSOT 입력**: `inception/requirements/trends-notifications.md`(RESOLVED)·`requirements.md` FR-47~48·C-9/C-10 · `stories.md` 에픽 13 US-TN1~3 · `unit-of-work.md` U15
> U14 전례를 따라 단일 파일로 통합한다. ⚠️ **실효 종속**: daily harvest 일시 중지(OQ-5) — 본 설계는 기존 코퍼스로 빌드/테스트 가능하게 잡되, 스케줄 배선은 harvest 재개 논의와 함께 확정한다.

## 1. Entity Model *(전부 owner-scoped, SEC-8)*

### FollowedTopic *(U15 소유)*
- `id` · `userId` · `topic: str` (명시 팔로우 주제 — U14/U9 관심 프로필과 별개, 교차 기록 금지)
- `embedding: vector` — **등록 시 1회** 기존 임베딩 포트(Bedrock, 코퍼스와 동일 모델/공간)로 생성·행에 저장; 주제 텍스트 수정 시에만 재임베딩
- `createdAt`

### DigestSettings *(U15 소유 — 사용자당 1행)*
- `userId` · `optedIn: bool` (**기본 false** — BR-TN1) · `cadence: "daily" | "weekly"` (기본 `daily`, 설정 UI 관리)
- `lastSentAt: datetime | null` — **발송 워터마크**: 다음 다이제스트는 이 시각 이후 harvest 신규분만 담는다(중복 수록 방지의 단일 기준)

### 발송 이력
- 다이제스트 발송 1건당 로그 행(`userId`, `sentAt`, `paperCount`) — 관측/멱등 확인용. 이메일 본문은 저장하지 않는다.

## 2. 매칭 계약 *(OQ-8 — 키워드/임베딩 유사도)*
- 후보 = harvest 신규분: `ingestedAt > lastSentAt`(첫 발송은 옵트인 시각 기준) 코퍼스 레코드.
- 매칭 = 기존 OpenSearch 인덱스에 **주제 임베딩 kNN**(코퍼스 임베딩 재사용) + 키워드 매치 보조, 유사도 **임계값 T** 이상만 수록.
  <!-- ponytail: T와 다이제스트당 상한 N(주제당 10·전체 20 기본)은 env 캘리브레이션 knob — 실데이터 정밀도 보고 조정. -->
- 수록 논문은 코퍼스 정책(C-1/C-6) 안 — 이메일에는 제목·초록 **링크백**만, 전문/초록 본문 미포함(BR-TN6).

## 3. 다이제스트 잡 *(배치 — 스케줄 배선은 유예)*
1. cadence 도래한 `optedIn=true` 사용자 순회 (BR-TN1: 미옵트인 접근 자체 없음).
2. 사용자별: FollowedTopic들로 §2 매칭 → 주제 간 dedupe → 상한 N 적용.
3. **빈 다이제스트 발송 안 함**(BR-TN2) — 워터마크도 전진시키지 않는다(다음 주기에 누적 포함).
4. plain list 렌더(제목·DocSuri 논문 페이지 링크) + **수신 해지 링크** → 기존 `EMAIL_PROVIDER` 심으로 발송(SES on `559352512800`).
5. 성공 시 `lastSentAt` 전진 + 이력 기록. **사용자별 실패 격리**(BR-TN3): 한 사용자 실패가 순회를 멈추지 않고, 실패 사용자는 워터마크 미전진으로 다음 주기에 자연 재시도 — 별도 재시도 큐 없음.
- **진입점**: 스케줄러 미확정이므로 `run_digest(now)` 를 CLI/관리 진입점으로 노출 — 지금 빌드/테스트 가능, harvest 재개 시 스케줄만 배선.

## 4. API Surface *(U15 모듈, U6 게이트웨이 경유 — 제안)*
| Method | Path | 동작 |
|---|---|---|
| GET/POST/DELETE | `/trends/follows` | 팔로우 주제 목록 조회/추가(등록 시 임베딩)/삭제 (US-TN1) |
| GET/PUT | `/trends/settings` | `optedIn`·`cadence` 조회/변경 — 변경 즉시 반영 (US-TN2) |
| POST | `/trends/unsubscribe` | **무로그인 해지**: 다이제스트 링크의 서명 토큰(owner-scoped·발송 시 생성)으로 `optedIn=false` 즉시 반영. RFC 8058 one-click(List-Unsubscribe) 호환 POST. |

## 5. Business Rules
- **BR-TN1**: `optedIn=false`(기본값)면 어떤 발송도 없다 — 옵트인 전 발송 경로 자체가 사용자를 선택하지 않는다.
- **BR-TN2**: 매칭 0건이면 미발송 + 워터마크 유지.
- **BR-TN3**: 발송 실패는 사용자 단위 격리, 비차단 — 워터마크 미전진이 곧 자연 재시도. 타 기능·타 사용자 무영향.
- **BR-TN4**: 해지는 즉시 반영 — 이메일 내 토큰 경로는 로그인 없이 동작하되 해당 수신자에게만 유효(서명 토큰), 설정 UI 토글과 동등.
- **BR-TN5**: 팔로우 목록과 U14/U9 관심 신호는 상호 무기록 — 어느 쪽도 다른 쪽을 읽거나 쓰지 않는다.
- **BR-TN6**: 이메일은 링크백 전용 — 논문 본문/초록 텍스트를 담지 않는다(C-1 재배포 경계).
- **BR-TN7**: 주제 임베딩은 등록/수정 시에만 — 다이제스트 실행 중 임베딩 호출 없음(비용·지연 상수화).

## 6. Testable Properties
- 옵트인 게이팅: `optedIn=false` 사용자는 잡 실행 후에도 발송 이력 0.
- 빈 다이제스트 억제 + 워터마크 불변 → 다음 주기 누적 수록.
- 워터마크 멱등: 동일 `now`로 잡 재실행 시 중복 발송 없음.
- 동일 코퍼스·윈도·주제 → 동일 매칭 결과(결정성; T·N 고정 시).
- 해지 토큰: 타 사용자 토큰 거부, 유효 토큰은 무로그인 즉시 `optedIn=false`.
- 사용자 A 발송 실패가 사용자 B 발송을 막지 않음.
- owner-scoping: 타인 팔로우 목록/설정 접근 불가(401/404).

## 7. Traceability
FR-47(§2·§3·§4 unsubscribe·BR-TN2/3/6) · FR-48(§1·§4 follows/settings·BR-TN1/5) · US-TN1(§1·§4) · US-TN2(BR-TN1/4) · US-TN3(§2·§3) · C-9(§2 harvest 소스·§3 EMAIL_PROVIDER) · C-10(범위) · C-1/C-6(BR-TN6) · SEC-8(§1·BR-TN4) · NFR-C1(비대상 — BR-TN7이 임베딩 비용 상수화)
