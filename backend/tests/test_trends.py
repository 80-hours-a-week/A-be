"""U15 Trends — functional-design §6 testable properties.

Everything runs on in-memory fakes (no live AWS/OpenSearch/SMTP): the search port is a
deterministic fixture, the email port a recorder, and BR-TN7 is asserted with a
call-counting embedding fake. HTTP-facing properties (authz fail-closed, owner-scoping, DTO
bounds, no-login unsubscribe) run through the app-shell TestClient like the U14 suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from docsuri_shared.authz import Principal, UserRole
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.modules.trends import controller
from backend.modules.trends.models import (
    MAX_TOPIC_LENGTH,
    MAX_TOPICS_PER_USER,
    DigestCadence,
    PaperMatch,
)
from backend.modules.trends.repository import InMemoryTrendsRepository
from backend.modules.trends.service import (
    DuplicateTopic,
    TopicLimitExceeded,
    TrendsConfig,
    TrendsService,
    UnsubscribeTokenSigner,
    render_digest_email,
)

T0 = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
CONFIG = TrendsConfig(match_threshold=0.5, per_topic_cap=10, digest_cap=20, app_url="https://app.test")
SIGNER = UnsubscribeTokenSigner("test-secret")


def _principal(user_id: str | None = None) -> Principal:
    return Principal(user_id=user_id or str(uuid4()), role=UserRole.USER)


# ── Fakes (deterministic — §6 결정성) ────────────────────────────────────────────────────────


class CountingEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    def embed_topic(self, text: str) -> list[float]:
        self.calls += 1
        return [1.0, 0.0, 0.0]


class FixtureSearch:
    """papers: list of (paperId, title, score, ingestedAt) — the window filter is applied
    exactly as the §2 contract demands (ingestedAt > since)."""

    def __init__(self, papers: list[tuple[str, str, float, datetime]]) -> None:
        self.papers = papers

    def match_topic(self, *, embedding, keywords, since, limit):
        hits = [
            PaperMatch(paperId=pid, title=title, score=score)
            for pid, title, score, ingested in self.papers
            if ingested > since
        ]
        return hits[:limit]


class RecordingEmail:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.sent: list[tuple[str, str, str, str]] = []
        self.fail_for = fail_for or set()

    def send(self, to, subject, text, html) -> bool:
        if to in self.fail_for:
            return False
        self.sent.append((to, subject, text, html))
        return True


class DictEmails:
    def __init__(self, emails: dict[str, str]) -> None:
        self.emails = emails

    def get_email(self, user_id: str) -> str | None:
        return self.emails.get(user_id)


def _service(repo, *, search=None, email=None, recipients=None, embedding=None) -> TrendsService:
    return TrendsService(
        repo,
        embedding_port=embedding or CountingEmbedding(),
        search_port=search or FixtureSearch([]),
        email_port=email or RecordingEmail(),
        recipient_emails=recipients or DictEmails({}),
        token_signer=SIGNER,
        config=CONFIG,
    )


def _opted_in_user(repo, user_id: str, *, topic: str = "graph neural networks") -> None:
    service = _service(repo)
    service.follow_topic(user_id, _follow_dto(topic))
    service.put_settings(user_id, True, DigestCadence.DAILY, now=T0)


def _follow_dto(topic: str):
    from backend.modules.trends.models import FollowTopicRequest

    return FollowTopicRequest(topic=topic)


def _paper(pid: str, score: float, ingested: datetime) -> tuple[str, str, float, datetime]:
    return (pid, f"Paper {pid}", score, ingested)


# ── Opt-in gating (BR-TN1) ───────────────────────────────────────────────────────────────────


def test_opted_out_user_never_selected_even_with_matches() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    service = _service(repo)
    service.follow_topic(user, _follow_dto("diffusion models"))
    # default settings: optedIn=False (BR-TN1) — user never even wrote a settings row
    email = RecordingEmail()
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=email,
        recipients=DictEmails({user: "a@test"}),
    )

    report = runner.run_digest(T0 + timedelta(days=1))

    assert report.usersConsidered == 0
    assert email.sent == []
    assert repo.list_send_log(user) == []


# ── Empty digest suppression + watermark accumulation (BR-TN2) ───────────────────────────────


def test_empty_digest_suppressed_watermark_unchanged_then_accumulates() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    _opted_in_user(repo, user)
    email = RecordingEmail()
    search = FixtureSearch([])  # nothing harvested yet at run 1
    runner = _service(repo, search=search, email=email, recipients=DictEmails({user: "a@test"}))

    run1 = runner.run_digest(T0 + timedelta(hours=25))  # window (T0, now): empty

    assert (run1.sent, run1.skippedEmpty) == (0, 1)
    assert email.sent == []
    assert repo.get_settings(user).lastSentAt is None  # watermark NOT advanced

    # a paper ingested at T0+10h lands in the corpus late (harvest lag). Had run 1 advanced
    # the watermark to T0+25h it would be lost; the kept watermark accumulates it into run 2.
    search.papers.append(_paper("2401.0001", 0.9, T0 + timedelta(hours=10)))
    run2 = runner.run_digest(T0 + timedelta(hours=49))

    assert run2.sent == 1
    assert len(email.sent) == 1
    assert repo.get_settings(user).lastSentAt == T0 + timedelta(hours=49)
    assert [r.paperCount for r in repo.list_send_log(user)] == [1]


def test_first_send_window_starts_at_opt_in_time() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    _opted_in_user(repo, user)  # opted in at T0
    email = RecordingEmail()
    runner = _service(
        repo,
        search=FixtureSearch(
            [
                _paper("2312.9999", 0.9, T0 - timedelta(days=3)),  # pre-opt-in: excluded
                _paper("2401.0001", 0.9, T0 + timedelta(hours=1)),
            ]
        ),
        email=email,
        recipients=DictEmails({user: "a@test"}),
    )

    report = runner.run_digest(T0 + timedelta(hours=2))

    assert report.sent == 1
    _, _, text, _ = email.sent[0]
    assert "2401.0001" in text
    assert "2312.9999" not in text


# ── Watermark idempotency (§6) ───────────────────────────────────────────────────────────────


def test_rerun_with_same_now_sends_no_duplicates() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    _opted_in_user(repo, user)
    email = RecordingEmail()
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=email,
        recipients=DictEmails({user: "a@test"}),
    )
    now = T0 + timedelta(hours=2)

    first = runner.run_digest(now)
    second = runner.run_digest(now)  # same logical time re-run

    assert first.sent == 1
    assert second.sent == 0
    assert second.skippedNotDue == 1
    assert len(email.sent) == 1
    assert len(repo.list_send_log(user)) == 1


# ── Matching determinism + caps + dedupe (§2/§6) ─────────────────────────────────────────────


def test_matching_is_deterministic_and_dedupes_across_topics() -> None:
    user = str(uuid4())
    papers = [
        _paper("2401.0002", 0.8, T0 + timedelta(hours=1)),
        _paper("2401.0001", 0.8, T0 + timedelta(hours=1)),  # tie → paperId asc
        _paper("2401.0003", 0.9, T0 + timedelta(hours=1)),
        _paper("2401.0004", 0.3, T0 + timedelta(hours=1)),  # below threshold T=0.5
    ]
    bodies = []
    for _ in range(2):  # identical corpus/window/topics, rebuilt from scratch each time
        repo = InMemoryTrendsRepository()
        service = _service(repo)
        service.follow_topic(user, _follow_dto("graph neural networks"))
        service.follow_topic(user, _follow_dto("message passing"))  # overlapping matches
        service.put_settings(user, True, DigestCadence.DAILY, now=T0)
        email = RecordingEmail()
        runner = _service(
            repo,
            search=FixtureSearch(papers),
            email=email,
            recipients=DictEmails({user: "a@test"}),
        )
        runner.run_digest(T0 + timedelta(hours=2))
        bodies.append(email.sent[0][2])

    assert bodies[0] == bodies[1]  # same corpus/window/topics → identical digest
    # dedupe: both topics matched the same 3 papers → each appears once, ordered by
    # (-score, paperId); the sub-threshold paper is excluded.
    body = bodies[0]
    assert body.index("2401.0003") < body.index("2401.0001") < body.index("2401.0002")
    assert body.count("papers/2401.0003") == 1  # one link despite two matching topics
    assert "2401.0004" not in body


def test_digest_cap_bounds_total_papers() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    _opted_in_user(repo, user)
    papers = [
        _paper(f"2401.{n:04d}", 0.9 - n * 0.001, T0 + timedelta(hours=1)) for n in range(40)
    ]
    email = RecordingEmail()
    runner = _service(
        repo, search=FixtureSearch(papers), email=email, recipients=DictEmails({user: "a@test"})
    )

    runner.run_digest(T0 + timedelta(hours=2))

    assert repo.list_send_log(user)[0].paperCount <= CONFIG.digest_cap


# ── BR-TN7: zero embedding calls during the digest run ───────────────────────────────────────


def test_run_digest_makes_zero_embedding_calls() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    embedding = CountingEmbedding()
    service = _service(repo, embedding=embedding)
    service.follow_topic(user, _follow_dto("diffusion models"))
    service.put_settings(user, True, DigestCadence.DAILY, now=T0)
    assert embedding.calls == 1  # embedded ONCE at registration

    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=RecordingEmail(),
        recipients=DictEmails({user: "a@test"}),
        embedding=embedding,
    )
    runner.run_digest(T0 + timedelta(hours=2))

    assert embedding.calls == 1  # digest used the STORED vector only


# ── Per-user failure isolation (BR-TN3) ──────────────────────────────────────────────────────


def test_one_users_failure_never_stops_the_loop_and_keeps_watermark() -> None:
    repo = InMemoryTrendsRepository()
    # sorted so user_a is visited first — proves a leading failure doesn't stop the loop
    user_a, user_b = sorted([str(uuid4()), str(uuid4())])
    _opted_in_user(repo, user_a)
    _opted_in_user(repo, user_b)
    email = RecordingEmail(fail_for={"a@test"})
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=email,
        recipients=DictEmails({user_a: "a@test", user_b: "b@test"}),
    )

    report = runner.run_digest(T0 + timedelta(hours=2))

    assert (report.sent, report.failed) == (1, 1)
    assert [to for to, *_ in email.sent] == ["b@test"]
    assert repo.get_settings(user_a).lastSentAt is None  # not advanced → natural retry
    assert repo.get_settings(user_b).lastSentAt == T0 + timedelta(hours=2)


# ── Unsubscribe token (BR-TN4/SEC-8) ─────────────────────────────────────────────────────────


def test_unsubscribe_token_flips_opt_in_and_tampered_token_rejected() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    service = _service(repo)
    service.put_settings(user, True, DigestCadence.DAILY, now=T0)
    token = service.issue_unsubscribe_token(user)

    from backend.modules.trends.service import InvalidUnsubscribeToken

    # a token signed with another secret (≒ forged for another recipient) is rejected
    forged = UnsubscribeTokenSigner("other-secret").issue(user, T0.isoformat())
    with pytest.raises(InvalidUnsubscribeToken):
        service.unsubscribe(forged)
    assert repo.get_settings(user).optedIn is True

    settings = service.unsubscribe(token)

    assert settings.optedIn is False
    # …and a later settings change invalidated any still-outstanding token of that vintage:
    service.put_settings(user, True, DigestCadence.DAILY)
    with pytest.raises(InvalidUnsubscribeToken):
        service.unsubscribe(token)


def test_unsubscribe_is_idempotent_for_already_opted_out() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    service = _service(repo)
    service.put_settings(user, True, DigestCadence.DAILY, now=T0)
    token = service.issue_unsubscribe_token(user)

    service.unsubscribe(token)
    again = service.unsubscribe(token)  # RFC 8058 one-click re-POST

    assert again.optedIn is False


# ── BR-TN6: email is link-back only ──────────────────────────────────────────────────────────


def test_digest_email_contains_titles_and_links_only() -> None:
    matches = [PaperMatch(paperId="2401.0001", title="Attention & Beyond", score=0.9)]

    subject, text, body_html = render_digest_email(
        matches, app_url="https://app.test", unsubscribe_url="https://app.test/u?token=t"
    )

    assert "Attention & Beyond" in text
    assert "https://app.test/papers/2401.0001" in text
    assert "https://app.test/u?token=t" in text
    assert "Attention &amp; Beyond" in body_html  # titles are HTML-escaped
    # PaperMatch carries no abstract field at all — BR-TN6 holds structurally; the rendered
    # body is exactly title + link lines + the unsubscribe link.
    assert "abstract" not in text.lower()


def test_sent_digest_links_to_frontend_unsubscribe_route() -> None:
    """Regression (unit review BLOCKING): the REAL run_digest path must emit the FE route
    `/unsubscribe?token=` — not the API path `/trends/unsubscribe` — in the email body."""
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    _opted_in_user(repo, user)
    email = RecordingEmail()
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=email,
        recipients=DictEmails({user: "a@test"}),
    )

    report = runner.run_digest(T0 + timedelta(hours=2))

    assert report.sent == 1
    _, _, text, body_html = email.sent[0]
    for body in (text, body_html):
        assert "/unsubscribe?token=" in body
        assert "/trends/unsubscribe" not in body


class OptOutTriggeringEmail(RecordingEmail):
    """Simulates a mid-sweep opt-out: delivering user A's digest flips user B's optedIn off
    (as a settings PUT / token unsubscribe landing while the loop is mid-flight would)."""

    def __init__(self, repo, flip_user: str) -> None:
        super().__init__()
        self._repo = repo
        self._flip_user = flip_user

    def send(self, to, subject, text, html) -> bool:
        result = super().send(to, subject, text, html)
        flip_at = T0 + timedelta(hours=2)
        self._repo.put_settings(self._flip_user, False, DigestCadence.DAILY, flip_at)
        return result


def test_opt_out_mid_sweep_prevents_that_sweeps_send() -> None:
    repo = InMemoryTrendsRepository()
    user_a, user_b = str(uuid4()), str(uuid4())  # insertion order: A is visited first
    _opted_in_user(repo, user_a)
    _opted_in_user(repo, user_b)
    email = OptOutTriggeringEmail(repo, flip_user=user_b)
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=email,
        recipients=DictEmails({user_a: "a@test", user_b: "b@test"}),
    )

    report = runner.run_digest(T0 + timedelta(hours=2))

    assert report.sent == 1
    assert [to for to, *_ in email.sent] == ["a@test"]  # B receives NOTHING
    assert repo.list_send_log(user_b) == []
    assert repo.get_settings(user_b).lastSentAt is None  # watermark untouched


def test_commit_after_each_successfully_sent_user() -> None:
    """Durability boundary: one commit per SENT user (email is irreversible — a mid-sweep
    crash must not roll delivered watermarks back into a re-send)."""
    repo = InMemoryTrendsRepository()
    sent_user, empty_user = str(uuid4()), str(uuid4())
    _opted_in_user(repo, sent_user)
    service = _service(repo)  # empty_user opts in but follows nothing → empty digest
    service.put_settings(empty_user, True, DigestCadence.DAILY, now=T0)
    runner = _service(
        repo,
        search=FixtureSearch([_paper("2401.0001", 0.9, T0 + timedelta(hours=1))]),
        email=RecordingEmail(),
        recipients=DictEmails({sent_user: "a@test", empty_user: "b@test"}),
    )

    report = runner.run_digest(T0 + timedelta(hours=2))

    assert (report.sent, report.skippedEmpty) == (1, 1)
    assert repo.commits == 1  # committed for the sent user only


# ── HTTP surface: authz fail-closed, owner-scoping, DTO bounds, no-login unsubscribe ─────────


def _client(principal: Principal | None = None, repo=None, signer=None) -> TestClient:
    app = create_app(Settings(env="test", database_url="sqlite://"))
    if principal is not None:
        app.dependency_overrides[controller.get_principal] = lambda: principal
    if repo is not None:
        app.dependency_overrides[controller.get_repo] = lambda: repo
    if signer is not None:
        app.dependency_overrides[controller.get_token_signer] = lambda: signer
    return TestClient(app)


def test_trends_mounts_in_app_shell() -> None:
    app = create_app(Settings(env="test", database_url="sqlite://"))
    assert "trends" in app.state.mount_result.mounted


def test_unauthenticated_requests_fail_closed_401() -> None:
    client = _client()  # no principal on request.state
    assert client.get("/trends/follows").status_code == 401
    assert client.post("/trends/follows", json={"topic": "x"}).status_code == 401
    assert client.get("/trends/settings").status_code == 401
    assert client.put(
        "/trends/settings", json={"optedIn": True, "cadence": "daily"}
    ).status_code == 401


def test_follow_crud_and_owner_scoped_delete() -> None:
    repo = InMemoryTrendsRepository()
    alice, bob = _principal(), _principal()
    alice_client = _client(alice, repo=repo)
    bob_client = _client(bob, repo=repo)

    created = alice_client.post("/trends/follows", json={"topic": "  graph  learning "})
    assert created.status_code == 201
    assert created.json()["topic"] == "graph learning"  # whitespace normalized
    assert "embedding" not in created.json()  # internal field never serialized
    topic_id = created.json()["id"]

    # cross-user delete: bob cannot see or delete alice's topic (404, owner-scoped)
    assert bob_client.delete(f"/trends/follows/{topic_id}").status_code == 404
    assert bob_client.get("/trends/follows").json()["topics"] == []

    deleted = alice_client.delete(f"/trends/follows/{topic_id}")
    assert deleted.status_code == 200
    assert deleted.json()["topics"] == []


def test_follow_dto_bounds_yield_422() -> None:
    client = _client(_principal())
    assert client.post("/trends/follows", json={"topic": ""}).status_code == 422
    assert client.post("/trends/follows", json={"topic": "   "}).status_code == 422
    assert (
        client.post("/trends/follows", json={"topic": "x" * (MAX_TOPIC_LENGTH + 1)}).status_code
        == 422
    )
    assert client.post("/trends/follows", json={}).status_code == 422
    assert (
        client.post("/trends/follows", json={"topic": "ok", "extra": 1}).status_code == 422
    )  # extra=forbid
    assert (
        client.put("/trends/settings", json={"optedIn": True, "cadence": "hourly"}).status_code
        == 422
    )  # cadence outside daily|weekly


def test_follow_cap_and_duplicate_are_409() -> None:
    client = _client(_principal())
    for n in range(MAX_TOPICS_PER_USER):
        assert client.post("/trends/follows", json={"topic": f"topic {n}"}).status_code == 201
    assert client.post("/trends/follows", json={"topic": "one more"}).status_code == 409
    # duplicate check fires before the cap check message-wise; assert on an under-cap client
    dup_client = _client(_principal())
    assert dup_client.post("/trends/follows", json={"topic": "Same Topic"}).status_code == 201
    assert dup_client.post("/trends/follows", json={"topic": "same topic"}).status_code == 409


def test_settings_roundtrip_defaults_opted_out() -> None:
    client = _client(_principal())

    initial = client.get("/trends/settings").json()
    assert initial == {"optedIn": False, "cadence": "daily", "lastSentAt": None}  # BR-TN1

    updated = client.put("/trends/settings", json={"optedIn": True, "cadence": "weekly"})
    assert updated.status_code == 200
    assert updated.json()["optedIn"] is True
    assert client.get("/trends/settings").json()["cadence"] == "weekly"


def test_unsubscribe_endpoint_needs_no_login_and_never_5xx() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    service = TrendsService(repo, token_signer=SIGNER, config=CONFIG)
    service.put_settings(user, True, DigestCadence.DAILY, now=T0)
    token = service.issue_unsubscribe_token(user)
    client = _client(principal=None, repo=repo, signer=SIGNER)  # NO principal — no login

    ok = client.post("/trends/unsubscribe", json={"token": token})
    assert ok.status_code == 200
    assert ok.json() == {"optedIn": False}
    assert repo.get_settings(user).optedIn is False

    for bad in ["garbage", "a.b", token[:-4] + "beef"]:
        response = client.post("/trends/unsubscribe", json={"token": bad})
        assert response.status_code == 400  # 4xx, never 5xx
    assert client.post("/trends/unsubscribe", json={}).status_code == 422


def test_service_raises_on_cap_and_duplicate() -> None:
    repo = InMemoryTrendsRepository()
    user = str(uuid4())
    service = _service(repo)
    service.follow_topic(user, _follow_dto("alpha"))
    with pytest.raises(DuplicateTopic):
        service.follow_topic(user, _follow_dto("Alpha"))
    for n in range(MAX_TOPICS_PER_USER - 1):
        service.follow_topic(user, _follow_dto(f"t{n}"))
    with pytest.raises(TopicLimitExceeded):
        service.follow_topic(user, _follow_dto("overflow"))
