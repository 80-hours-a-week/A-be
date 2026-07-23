"""U15 Trends — persistence for followed topics, digest settings, and the send log (SEC-8).

Mirrors the U14 repository pattern: a ``Protocol`` port, the in-memory mock-first default, and
the SQL adapter mapping 1:1 to ``migrations/001_create_trends_tables.sql``. ``user_id`` is a
required argument on every method so an adapter structurally cannot return another owner's rows.

Watermark contract (functional-design §1/§3): ``advance_watermark`` moves ``lastSentAt`` ONLY —
it must NOT bump ``updatedAt``, because ``updatedAt`` versions the signed unsubscribe token and
the token embedded in the just-sent email has to stay valid. ``put_settings`` (a user-visible
change) is what bumps ``updatedAt`` and thereby invalidates outstanding tokens.
"""

from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Protocol

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import (
    DigestCadence,
    DigestSendRecord,
    DigestSettings,
    FollowedTopic,
    utc_now,
)


class TrendsRepository(Protocol):
    # follows (US-TN1)
    def list_topics(self, user_id: str) -> list[FollowedTopic]: ...
    def add_topic(self, user_id: str, topic: FollowedTopic) -> FollowedTopic: ...
    def delete_topic(self, user_id: str, topic_id: str) -> bool: ...

    # digest settings (US-TN2)
    def get_settings(self, user_id: str) -> DigestSettings | None: ...
    def put_settings(
        self, user_id: str, opted_in: bool, cadence: DigestCadence, now: datetime
    ) -> DigestSettings: ...
    def advance_watermark(self, user_id: str, sent_at: datetime) -> None: ...
    def list_opted_in(self) -> list[DigestSettings]: ...

    # send log (§1 발송 이력)
    def record_send(self, user_id: str, sent_at: datetime, paper_count: int) -> None: ...
    def list_send_log(self, user_id: str) -> list[DigestSendRecord]: ...

    # durability boundary: run_digest calls this after EACH successfully sent user so a
    # mid-sweep crash cannot roll back delivered users' watermarks (email is irreversible —
    # a rolled-back watermark means a duplicate send next run).
    def commit(self) -> None: ...


def _apply_settings_change(
    current: DigestSettings | None,
    user_id: str,
    opted_in: bool,
    cadence: DigestCadence,
    now: datetime,
) -> DigestSettings:
    """Pure settings transition shared by both adapters. An opt-OUT→opt-IN transition resets
    the watermark and re-anchors ``optedInAt`` so the first digest after (re-)opt-in covers
    papers ingested after the opt-in time (§2 첫 발송 기준), not the opted-out gap."""
    base = current or DigestSettings(userId=user_id, updatedAt=now)
    became_opted_in = opted_in and not base.optedIn
    return base.model_copy(
        update={
            "optedIn": opted_in,
            "cadence": cadence,
            "optedInAt": now if became_opted_in else base.optedInAt,
            "lastSentAt": None if became_opted_in else base.lastSentAt,
            "updatedAt": now,
        }
    )


class InMemoryTrendsRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._topics: dict[str, list[FollowedTopic]] = {}
        self._settings: dict[str, DigestSettings] = {}
        self._send_log: dict[str, list[DigestSendRecord]] = {}
        # in-memory writes are immediate; the counter lets tests spy the durability boundary
        self.commits = 0

    def list_topics(self, user_id: str) -> list[FollowedTopic]:
        with self._lock:
            return list(self._topics.get(user_id, []))

    def add_topic(self, user_id: str, topic: FollowedTopic) -> FollowedTopic:
        with self._lock:
            rows = self._topics.setdefault(user_id, [])
            rows.append(topic)
            return topic

    def delete_topic(self, user_id: str, topic_id: str) -> bool:
        with self._lock:
            rows = self._topics.get(user_id, [])
            kept = [row for row in rows if row.id != topic_id]
            self._topics[user_id] = kept
            return len(kept) != len(rows)

    def get_settings(self, user_id: str) -> DigestSettings | None:
        with self._lock:
            return self._settings.get(user_id)

    def put_settings(
        self, user_id: str, opted_in: bool, cadence: DigestCadence, now: datetime
    ) -> DigestSettings:
        with self._lock:
            updated = _apply_settings_change(
                self._settings.get(user_id), user_id, opted_in, cadence, now
            )
            self._settings[user_id] = updated
            return updated

    def advance_watermark(self, user_id: str, sent_at: datetime) -> None:
        with self._lock:
            current = self._settings.get(user_id)
            if current is not None:  # watermark only — updatedAt untouched (token stays valid)
                self._settings[user_id] = current.model_copy(update={"lastSentAt": sent_at})

    def list_opted_in(self) -> list[DigestSettings]:
        with self._lock:
            return [s for s in self._settings.values() if s.optedIn]

    def record_send(self, user_id: str, sent_at: datetime, paper_count: int) -> None:
        with self._lock:
            self._send_log.setdefault(user_id, []).append(
                DigestSendRecord(userId=user_id, sentAt=sent_at, paperCount=paper_count)
            )

    def list_send_log(self, user_id: str) -> list[DigestSendRecord]:
        with self._lock:
            return list(self._send_log.get(user_id, []))

    def commit(self) -> None:
        with self._lock:
            self.commits += 1


class Base(DeclarativeBase):
    pass


class FollowedTopicTable(Base):
    __tablename__ = "followed_topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DigestSettingsTable(Base):
    __tablename__ = "digest_settings"

    owner_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DigestSendLogTable(Base):
    __tablename__ = "digest_send_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paper_count: Mapped[int] = mapped_column(Integer, nullable=False)


def _topic_from_row(row: FollowedTopicTable) -> FollowedTopic:
    return FollowedTopic(
        id=row.id,
        userId=row.owner_id,
        topic=row.topic,
        embedding=list(row.embedding or []),
        createdAt=row.created_at,
    )


def _settings_from_row(row: DigestSettingsTable) -> DigestSettings:
    return DigestSettings(
        userId=row.owner_id,
        optedIn=row.opted_in,
        cadence=DigestCadence(row.cadence),
        lastSentAt=row.last_sent_at,
        optedInAt=row.opted_in_at,
        updatedAt=row.updated_at,
    )


class SqlTrendsRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_topics(self, user_id: str) -> list[FollowedTopic]:
        rows = self._s.scalars(
            select(FollowedTopicTable)
            .where(FollowedTopicTable.owner_id == user_id)
            .order_by(FollowedTopicTable.created_at, FollowedTopicTable.id)
        ).all()
        return [_topic_from_row(row) for row in rows]

    def add_topic(self, user_id: str, topic: FollowedTopic) -> FollowedTopic:
        row = FollowedTopicTable(
            id=topic.id,
            owner_id=user_id,
            topic=topic.topic,
            embedding=list(topic.embedding),
            created_at=topic.createdAt,
        )
        self._s.add(row)
        self._s.flush()
        return _topic_from_row(row)

    def delete_topic(self, user_id: str, topic_id: str) -> bool:
        row = self._s.get(FollowedTopicTable, topic_id)
        if row is None or row.owner_id != user_id:  # owner-scoped: a foreign id is "not found"
            return False
        self._s.delete(row)
        self._s.flush()
        return True

    def get_settings(self, user_id: str) -> DigestSettings | None:
        row = self._s.get(DigestSettingsTable, user_id)
        return _settings_from_row(row) if row else None

    def put_settings(
        self, user_id: str, opted_in: bool, cadence: DigestCadence, now: datetime
    ) -> DigestSettings:
        row = self._s.get(DigestSettingsTable, user_id)
        updated = _apply_settings_change(
            _settings_from_row(row) if row else None, user_id, opted_in, cadence, now
        )
        if row is None:
            row = DigestSettingsTable(owner_id=user_id)
            self._s.add(row)
        row.opted_in = updated.optedIn
        row.cadence = updated.cadence.value
        row.last_sent_at = updated.lastSentAt
        row.opted_in_at = updated.optedInAt
        row.updated_at = updated.updatedAt
        self._s.flush()
        return _settings_from_row(row)

    def advance_watermark(self, user_id: str, sent_at: datetime) -> None:
        row = self._s.get(DigestSettingsTable, user_id)
        if row is not None:  # watermark only — updated_at untouched (token stays valid)
            row.last_sent_at = sent_at
            self._s.flush()

    def list_opted_in(self) -> list[DigestSettings]:
        rows = self._s.scalars(
            select(DigestSettingsTable)
            .where(DigestSettingsTable.opted_in.is_(True))
            .order_by(DigestSettingsTable.owner_id)
        ).all()
        return [_settings_from_row(row) for row in rows]

    def record_send(self, user_id: str, sent_at: datetime, paper_count: int) -> None:
        record = DigestSendRecord(userId=user_id, sentAt=sent_at, paperCount=paper_count)
        self._s.add(
            DigestSendLogTable(
                id=record.id, owner_id=user_id, sent_at=sent_at, paper_count=paper_count
            )
        )
        self._s.flush()

    def list_send_log(self, user_id: str) -> list[DigestSendRecord]:
        rows = self._s.scalars(
            select(DigestSendLogTable)
            .where(DigestSendLogTable.owner_id == user_id)
            .order_by(DigestSendLogTable.sent_at, DigestSendLogTable.id)
        ).all()
        return [
            DigestSendRecord(
                id=row.id, userId=row.owner_id, sentAt=row.sent_at, paperCount=row.paper_count
            )
            for row in rows
        ]

    def commit(self) -> None:
        self._s.commit()


__all__ = [
    "InMemoryTrendsRepository",
    "SqlTrendsRepository",
    "TrendsRepository",
    "utc_now",
]
