# U15 Trends/Notifications — NFR Requirements

> **상태**: 🟡 DRAFT 제안 (2026-07-23) · 신규 NFR 없음 — 기존 NFR의 U15 적용만 구체화한다 (`inception/requirements/trends-notifications.md` NFR 절 준수).

| 기존 NFR | U15 적용 |
|---|---|
| **SEC-8** | 팔로우 목록·설정·발송 이력 owner-scoped. 해지 토큰은 수신자 한정 서명 토큰(무로그인 경로의 유일한 인증) — 발송 시 생성, 설정 변경으로 무효화 가능해야 한다. |
| **NFR-C1** | LLM 무포함(OQ-4) → 비대상. 임베딩 비용은 주제 등록/수정 시 1회로 상수화(BR-TN7) — 다이제스트 실행 중 모델 호출 0. |
| **C-1/C-6** | 이메일은 코퍼스 정책 내 논문의 링크백 전용(BR-TN6) — 본문/초록 텍스트 재배포 없음. |

## 배포/인프라
- **신규 배포 단위 없음(로컬 서빙 시대)**: API 모듈(①) + 배치 잡은 `run_digest(now)` CLI/관리 진입점 — 스케줄 배선은 harvest 재개 논의와 함께(OQ-5). AWS 복귀 시에만 잡 유닛(③) 검토.
- **신규 인프라 최소**: Postgres 테이블 2~3개(followed_topics·digest_settings·발송 이력, 마이그레이션 1건). 매칭은 기존 OpenSearch kNN 재사용 — 신규 인덱스 없음.
- **이메일(OQ-6 결정)**: SES on `559352512800`, 기존 `EMAIL_PROVIDER` 심 경유. ⚠️ 운영 후속 2건 — (a) 신규 계정 SES sandbox → **production access 신청**, (b) 로컬 서빙에는 task IAM role이 없으므로 **스코프드 IAM 자격증명**(예: `ses:SendEmail` 한정) 방식 구현 시 확정. Resend는 심 특성상 env 폴백으로 자연 잔존.

## 캘리브레이션
- 유사도 임계값 **T** · 다이제스트 상한 **N**(주제당/전체) — env 오버라이드, 실데이터 정밀도/노이즈 보고 조정 (functional-design §2).
