"""U15 Trends — service layer: follows CRUD, settings, unsubscribe tokens, and the digest job.

Injection seams (all ``Protocol`` ports with safe local defaults — no new dependencies):
  • ``TopicEmbeddingPort`` — called ONCE per topic at registration (and only on a future topic
    edit). ``run_digest`` never touches it (BR-TN7); the CLI even wires a refusing port so a
    regression fails loudly instead of silently billing Bedrock.
  • ``TrendSearchPort`` — kNN by the STORED topic embedding + keyword assist over papers
    ingested after ``since`` (§2 matching contract). Threshold T / caps N live in
    ``TrendsConfig`` (env: DOCSURI_TRENDS_MATCH_THRESHOLD / _TOPIC_CAP / _DIGEST_CAP).
  • ``DigestEmailPort`` / ``RecipientEmailPort`` — the existing EMAIL_PROVIDER seam, adapted in
    the CLI/wiring; tests inject recorders.

Watermark semantics (§3, BR-TN1~3): only opted-in users on a due cadence are visited; an empty
digest sends nothing AND leaves ``lastSentAt`` unchanged (accumulates into the next cycle); a
successful send advances the watermark + writes the send log; any per-user failure is isolated
— the unchanged watermark IS the retry mechanism (no queue).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .models import (
    MAX_TOPICS_PER_USER,
    DigestCadence,
    DigestRunReport,
    DigestSettings,
    FollowedTopic,
    FollowTopicRequest,
    PaperMatch,
    utc_now,
)
from .repository import TrendsRepository

log = logging.getLogger("docsuri.backend.trends")


# ── Errors (controller maps these to 4xx — never 5xx on the unsubscribe path) ────────────────


class TrendsError(Exception):
    pass


class TopicLimitExceeded(TrendsError):
    pass


class DuplicateTopic(TrendsError):
    pass


class InvalidUnsubscribeToken(TrendsError):
    pass


# ── Ports ────────────────────────────────────────────────────────────────────────────────────


class TopicEmbeddingPort(Protocol):
    def embed_topic(self, text: str) -> list[float]: ...


class TrendSearchPort(Protocol):
    def match_topic(
        self,
        *,
        embedding: list[float],
        keywords: list[str],
        since: datetime,
        limit: int,
    ) -> list[PaperMatch]: ...


class DigestEmailPort(Protocol):
    def send(self, to: str, subject: str, text: str, html: str) -> bool: ...


class RecipientEmailPort(Protocol):
    def get_email(self, user_id: str) -> str | None: ...


# ── Safe local defaults (memory mode / tests — deterministic, no AWS) ────────────────────────

_FAKE_EMBEDDING_DIM = 8


class DeterministicFakeEmbedding:
    """Local stand-in for the Bedrock query embedder: a stable hash-derived vector so the
    memory mode stays deterministic (§6 결정성). NOT the corpus space — real matching requires
    the wired Bedrock embedder."""

    def embed_topic(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.strip().lower().encode()).digest()
        return [byte / 255.0 for byte in digest[:_FAKE_EMBEDDING_DIM]]


class NoopTrendSearch:
    """Default search port: no corpus configured → no candidates → BR-TN2 suppresses sends."""

    def match_topic(
        self, *, embedding: list[float], keywords: list[str], since: datetime, limit: int
    ) -> list[PaperMatch]:
        return []


class ConsoleDigestEmail:
    """Mock-first email port (mirrors MockEmailClient): logs, never sends, reports success."""

    def send(self, to: str, subject: str, text: str, html: str) -> bool:
        log.info("[MOCK DIGEST EMAIL] To: [redacted] Subject: %s", subject)
        return True


class NullRecipientEmails:
    def get_email(self, user_id: str) -> str | None:
        return None


class RefusingEmbeddingPort:
    """Wired into ``run_digest`` entrypoints: BR-TN7 says the digest makes ZERO embedding
    calls, so any call here is a contract violation — fail loudly."""

    def embed_topic(self, text: str) -> list[float]:
        raise RuntimeError("BR-TN7 violation: embedding was called during the digest run")


# ── Config (env calibration knobs — nfr-requirements §캘리브레이션) ──────────────────────────

_DEFAULT_MATCH_THRESHOLD = 0.30
_DEFAULT_TOPIC_CAP = 10
_DEFAULT_DIGEST_CAP = 20

# Cadence due-gates with slack so a real daily/weekly scheduler drifting a few hours early
# still fires, while an immediate re-run with the SAME `now` is never due (§6 멱등성).
_DAILY_MIN_GAP = timedelta(hours=20)
_WEEKLY_MIN_GAP = timedelta(days=6, hours=12)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        log.warning("trends: invalid %s ignored (default %s)", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        log.warning("trends: invalid %s ignored (default %s)", name, default)
        return default


@dataclass(frozen=True)
class TrendsConfig:
    """Calibration knobs (threshold T + caps N, functional-design §2) + link base."""

    match_threshold: float = _DEFAULT_MATCH_THRESHOLD
    per_topic_cap: int = _DEFAULT_TOPIC_CAP
    digest_cap: int = _DEFAULT_DIGEST_CAP
    app_url: str = ""

    @classmethod
    def from_env(cls) -> TrendsConfig:
        return cls(
            match_threshold=_env_float(
                "DOCSURI_TRENDS_MATCH_THRESHOLD", _DEFAULT_MATCH_THRESHOLD
            ),
            per_topic_cap=_env_int("DOCSURI_TRENDS_TOPIC_CAP", _DEFAULT_TOPIC_CAP),
            digest_cap=_env_int("DOCSURI_TRENDS_DIGEST_CAP", _DEFAULT_DIGEST_CAP),
            app_url=os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/"),
        )


# ── Unsubscribe token (SEC-8/BR-TN4 — stdlib hmac, no new deps) ──────────────────────────────


class UnsubscribeTokenSigner:
    """Signed, owner-scoped unsubscribe token: HMAC-SHA256 over ``user_id|settings_version``.

    The version is the settings row's ``updatedAt`` — any user-visible settings change (PUT or
    a prior unsubscribe) rotates it, invalidating outstanding tokens (nfr-requirements SEC-8).
    A watermark advance does NOT rotate it, so the token in the just-sent digest stays valid.
    """

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("unsubscribe token secret must be non-empty")
        self._secret = secret.encode()

    def issue(self, user_id: str, settings_version: str) -> str:
        payload = f"{user_id}|{settings_version}".encode()
        mac = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + mac

    def verify(self, token: str) -> tuple[str, str] | None:
        """→ (user_id, settings_version) when the signature holds; None otherwise."""
        encoded, sep, mac = token.partition(".")
        if not sep:
            return None
        try:
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (binascii.Error, ValueError):
            return None
        expected = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            return None
        user_id, sep, version = payload.decode(errors="replace").partition("|")
        if not sep or not user_id:
            return None
        return user_id, version


# Process-stable ephemeral fallback: without DOCSURI_TRENDS_UNSUBSCRIBE_KEY, tokens survive
# within one process (dev/tests) but not restarts — an expired-token 4xx, never a 5xx.
_EPHEMERAL_SECRET = secrets.token_hex(32)


def build_token_signer() -> UnsubscribeTokenSigner:
    secret = os.getenv("DOCSURI_TRENDS_UNSUBSCRIBE_KEY", "").strip()
    if not secret:
        log.warning(
            "trends: DOCSURI_TRENDS_UNSUBSCRIBE_KEY unset — using a process-ephemeral "
            "secret (unsubscribe links break across restarts)"
        )
        secret = _EPHEMERAL_SECRET
    return UnsubscribeTokenSigner(secret)


# ── Digest email rendering (BR-TN6: titles + links ONLY — no abstract/body text) ─────────────


def render_digest_email(
    matches: list[PaperMatch], *, app_url: str, unsubscribe_url: str
) -> tuple[str, str, str]:
    """(subject, text, html) — plain list of title + DocSuri paper-page link + the mandatory
    unsubscribe link (§3). ``PaperMatch`` carries no abstract text, so BR-TN6 holds by type."""
    subject = f"[DocSuri] 새 논문 다이제스트 ({len(matches)}건)"
    lines = [f"- {m.title}\n  {app_url}/papers/{m.paperId}" for m in matches]
    body_text = (
        "팔로우 중인 주제에 새 논문이 들어왔습니다.\n\n"
        + "\n".join(lines)
        + f"\n\n수신을 원치 않으시면 다음 링크로 해지할 수 있습니다:\n{unsubscribe_url}\n"
    )
    items = "".join(
        f'<li><a href="{app_url}/papers/{m.paperId}">{html.escape(m.title)}</a></li>'
        for m in matches
    )
    body_html = f"""
        <html>
            <body>
                <h3>팔로우 중인 주제에 새 논문이 들어왔습니다</h3>
                <ul>{items}</ul>
                <p><a href="{unsubscribe_url}">다이제스트 수신 해지</a></p>
            </body>
        </html>
    """
    return subject, body_text, body_html


# ── Service ──────────────────────────────────────────────────────────────────────────────────


class TrendsService:
    def __init__(
        self,
        repo: TrendsRepository,
        *,
        embedding_port: TopicEmbeddingPort | None = None,
        search_port: TrendSearchPort | None = None,
        email_port: DigestEmailPort | None = None,
        recipient_emails: RecipientEmailPort | None = None,
        token_signer: UnsubscribeTokenSigner | None = None,
        config: TrendsConfig | None = None,
        observability=None,
    ) -> None:
        self._repo = repo
        self._embedding = embedding_port or DeterministicFakeEmbedding()
        self._search = search_port or NoopTrendSearch()
        self._email = email_port or ConsoleDigestEmail()
        self._recipients = recipient_emails or NullRecipientEmails()
        self._signer = token_signer or build_token_signer()
        self._config = config or TrendsConfig.from_env()
        self._observability = observability

    # ── follows (US-TN1) ─────────────────────────────────────────────────────────────────

    def list_follows(self, user_id: str) -> list[FollowedTopic]:
        return self._repo.list_topics(user_id)

    def follow_topic(self, user_id: str, dto: FollowTopicRequest) -> FollowedTopic:
        """Register a followed topic — the ONE place the embedding port is called (BR-TN7).
        The embedding is deterministic for a given topic text (same model, same input), so
        re-registering after a delete reproduces the same vector."""
        existing = self._repo.list_topics(user_id)
        if any(row.topic.casefold() == dto.topic.casefold() for row in existing):
            raise DuplicateTopic(dto.topic)
        if len(existing) >= MAX_TOPICS_PER_USER:
            raise TopicLimitExceeded(str(MAX_TOPICS_PER_USER))
        topic = FollowedTopic(
            userId=user_id,
            topic=dto.topic,
            embedding=list(self._embedding.embed_topic(dto.topic)),
        )
        return self._repo.add_topic(user_id, topic)

    def unfollow_topic(self, user_id: str, topic_id: str) -> bool:
        return self._repo.delete_topic(user_id, topic_id)

    # ── settings (US-TN2) ────────────────────────────────────────────────────────────────

    def get_settings(self, user_id: str) -> DigestSettings:
        return self._repo.get_settings(user_id) or DigestSettings(userId=user_id)

    def put_settings(
        self, user_id: str, opted_in: bool, cadence: DigestCadence, now: datetime | None = None
    ) -> DigestSettings:
        return self._repo.put_settings(user_id, opted_in, cadence, now or utc_now())

    # ── unsubscribe token (BR-TN4/SEC-8) ─────────────────────────────────────────────────

    def issue_unsubscribe_token(self, user_id: str) -> str:
        """Owner-scoped signed token minted at send time (§4). Bound to the CURRENT settings
        version so any later settings change invalidates it."""
        settings = self.get_settings(user_id)
        return self._signer.issue(user_id, settings.updatedAt.isoformat())

    def unsubscribe(self, token: str) -> DigestSettings:
        """No-login opt-out (BR-TN4): the signature alone authenticates the recipient. An
        already-opted-out user is an idempotent success (RFC 8058 one-click re-POSTs); a stale
        version on an opted-in user is rejected — the settings change revoked the token."""
        verified = self._signer.verify(token)
        if verified is None:
            raise InvalidUnsubscribeToken("bad signature")
        user_id, version = verified
        settings = self._repo.get_settings(user_id)
        if settings is None:
            raise InvalidUnsubscribeToken("unknown settings")
        if not settings.optedIn:
            return settings  # idempotent: repeated one-click POSTs succeed without churn
        if settings.updatedAt.isoformat() != version:
            raise InvalidUnsubscribeToken("stale token (settings changed since issuance)")
        return self._repo.put_settings(user_id, False, settings.cadence, utc_now())

    # ── digest job (§3 — CLI entrypoint; scheduler wiring deferred per OQ-5) ─────────────

    def run_digest(self, now: datetime) -> DigestRunReport:
        """One batch sweep at logical time ``now``. Deterministic given the repo, the search
        port, and ``now`` (§6): candidate matching uses only STORED topic embeddings — zero
        embedding calls (BR-TN7)."""
        report = DigestRunReport(ranAt=now)
        for settings in self._repo.list_opted_in():  # BR-TN1: 미옵트인은 선택 자체가 안 됨
            report.usersConsidered += 1
            try:
                outcome = self._run_user(settings, now)
            except Exception:  # noqa: BLE001 — BR-TN3: per-user isolation, loop never stops
                log.warning(
                    "trends: digest failed for a user (watermark kept → natural retry)",
                    exc_info=True,
                )
                self._emit_metric("trends.digest_user_failure")
                report.failed += 1
                continue
            if outcome == "sent":
                report.sent += 1
            elif outcome == "not_due":
                report.skippedNotDue += 1
            elif outcome == "empty":
                report.skippedEmpty += 1
            else:
                report.failed += 1
        return report

    def _run_user(self, settings: DigestSettings, now: datetime) -> str:
        if not self._is_due(settings, now):
            return "not_due"
        since = settings.lastSentAt or settings.optedInAt or settings.updatedAt
        matches = self._match_all_topics(settings.userId, since)
        if not matches:
            return "empty"  # BR-TN2: no send AND the watermark stays put (accumulates)
        to_email = self._recipients.get_email(settings.userId)
        if not to_email:
            log.warning("trends: no deliverable email for an opted-in user — will retry")
            return "failed"
        token = self.issue_unsubscribe_token(settings.userId)
        unsubscribe_url = f"{self._config.app_url}/trends/unsubscribe?token={token}"
        subject, text, body_html = render_digest_email(
            matches, app_url=self._config.app_url, unsubscribe_url=unsubscribe_url
        )
        if not self._email.send(to_email, subject, text, body_html):
            return "failed"  # watermark untouched → next cycle retries the same window
        self._repo.advance_watermark(settings.userId, now)
        self._repo.record_send(settings.userId, now, len(matches))
        self._emit_metric("trends.digest_sent", float(len(matches)))
        return "sent"

    def _match_all_topics(self, user_id: str, since: datetime) -> list[PaperMatch]:
        """§2: per-topic kNN(stored embedding) + keyword assist over the post-``since`` window,
        threshold T, dedupe across topics (best score wins), global cap N, deterministic order
        (score desc, paperId asc)."""
        best: dict[str, PaperMatch] = {}
        for topic in self._repo.list_topics(user_id):
            candidates = self._search.match_topic(
                embedding=list(topic.embedding),
                keywords=[topic.topic],
                since=since,
                limit=self._config.per_topic_cap,
            )
            for match in candidates:
                if match.score < self._config.match_threshold:
                    continue
                current = best.get(match.paperId)
                if current is None or match.score > current.score:
                    best[match.paperId] = match
        ranked = sorted(best.values(), key=lambda m: (-m.score, m.paperId))
        return ranked[: self._config.digest_cap]

    @staticmethod
    def _is_due(settings: DigestSettings, now: datetime) -> bool:
        if settings.lastSentAt is None:
            return True  # never sent (or watermark reset on re-opt-in) → due
        gap = _WEEKLY_MIN_GAP if settings.cadence is DigestCadence.WEEKLY else _DAILY_MIN_GAP
        return now - settings.lastSentAt >= gap

    def _emit_metric(self, name: str, value: float = 1.0) -> None:
        emit = getattr(self._observability, "emit_metric", None)
        if emit is None:
            return
        try:
            emit(name, value, {})
        except Exception:  # noqa: BLE001 — observability must never break the digest
            pass
