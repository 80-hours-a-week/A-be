from __future__ import annotations

import os

# U11 웹레퍼런스 확장(§2) — 외부질의 위생 순수함수는 docsuri_shared로 승격됐다
# (evidence→novelty 역방향 의존 회피). #167 authz 이전과 동일한 동일성 보존 재수출:
# 기존 소비자(worker/adapters/테스트)는 이 모듈에서 같은 함수 객체를 계속 얻는다.
from docsuri_shared.external_query import (  # noqa: F401 — re-export (identity preserved)
    ALLOWED_EXTERNAL_HOSTS,
    is_safe_external_url,
    sanitize_external_query,
)


def encrypt_secret(plaintext: str) -> str:
    """US-NV8(#258)/SEC-8 — Notion 연결 토큰 대칭 암호화(Fernet). 키 미구성은 ValueError."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _fernet():
    from cryptography.fernet import Fernet

    key = os.getenv("DOCSURI_NOTION_TOKEN_KEY")
    if not key:
        raise ValueError("Notion 연결 저장소가 구성되지 않았습니다.")
    return Fernet(key.encode("utf-8"))
