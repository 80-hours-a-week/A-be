"""EvidenceSettings — env-driven config (U11 infrastructure-design).

``evidence_enabled`` gates real adapter assembly: the app-shell mounts U11 only when
the required deps (Bedrock model + S3 DocModel bucket) are configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Bedrock inference profile (TD-E3 / infrastructure-design §1)
DEFAULT_EVIDENCE_MODEL = 'global.anthropic.claude-sonnet-4-6'


def _env_flag(name: str, default: str = '') -> bool:
    return os.environ.get(name, default).lower() in ('1', 'true', 'yes')


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class EvidenceSettings:
    model_id: str
    docmodel_bucket: str | None   # S3 bucket (U1 소유 DocModel 버킷)
    region_name: str | None
    # 비동기 잡 경로 게이트 (BR-EV-6, NFR-P6)
    async_enabled: bool
    job_queue_url: str | None     # SQS evidence-agent-job-queue
    # U11 웹레퍼런스 확장(FR-49) — 성공 턴 post-hoc 웹 레퍼런스 동봉 게이트/상한/예산(§9)
    web_refs_enabled: bool = True
    web_refs_max: int = 5
    web_refs_timeout_s: float = 4.0
    openalex_mailto: str | None = None   # OpenAlex polite pool(권장)

    @property
    def evidence_enabled(self) -> bool:
        # 실 경로 = DocModel S3 버킷 필요 (Bedrock는 항상 사용 가능 가정)
        return bool(self.docmodel_bucket)

    @classmethod
    def from_env(cls) -> EvidenceSettings:
        return cls(
            model_id=os.environ.get('DOCSURI_EVIDENCE_MODEL_ID', DEFAULT_EVIDENCE_MODEL),
            docmodel_bucket=os.environ.get('DOCSURI_DOCMODEL_BUCKET'),
            region_name=os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION'),
            async_enabled=_env_flag('DOCSURI_EVIDENCE_ASYNC_ENABLED'),
            job_queue_url=os.environ.get('DOCSURI_EVIDENCE_JOB_QUEUE_URL'),
            web_refs_enabled=_env_flag('DOCSURI_WEB_REFS_ENABLED', default='true'),
            web_refs_max=_env_int('DOCSURI_WEB_REFS_MAX', 5),
            web_refs_timeout_s=_env_float('DOCSURI_WEB_REFS_TIMEOUT_S', 4.0),
            openalex_mailto=os.environ.get('DOCSURI_OPENALEX_MAILTO'),
        )
