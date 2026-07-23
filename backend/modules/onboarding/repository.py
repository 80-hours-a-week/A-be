"""U14 Onboarding — OnboardingStatus persistence (one owner-scoped table, SEC-8).

Mirrors U9's repository pattern: a ``Protocol`` port, the in-memory mock-first default, and the
SQL adapter mapping 1:1 to ``migrations/001_create_onboarding_status.sql``. ``user_id`` is a
required argument on every method so an adapter structurally cannot return another owner's row.
"""

from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Protocol

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import OnboardingState, OnboardingStatus, utc_now


class OnboardingRepository(Protocol):
    def get_status(self, user_id: str) -> OnboardingStatus | None: ...
    def set_state(self, user_id: str, state: OnboardingState) -> OnboardingStatus: ...


class InMemoryOnboardingRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._status: dict[str, OnboardingStatus] = {}

    def get_status(self, user_id: str) -> OnboardingStatus | None:
        with self._lock:
            return self._status.get(user_id)

    def set_state(self, user_id: str, state: OnboardingState) -> OnboardingStatus:
        with self._lock:
            current = self._status.get(user_id) or OnboardingStatus(userId=user_id)
            updated = current.model_copy(update={"state": state, "updatedAt": utc_now()})
            self._status[user_id] = updated
            return updated


class Base(DeclarativeBase):
    pass


class OnboardingStatusTable(Base):
    __tablename__ = "onboarding_status"

    owner_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    prompted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _status_from_row(row: OnboardingStatusTable) -> OnboardingStatus:
    return OnboardingStatus(
        userId=row.owner_id,
        state=OnboardingState(row.state),
        promptedAt=row.prompted_at,
        updatedAt=row.updated_at,
    )


class SqlOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_status(self, user_id: str) -> OnboardingStatus | None:
        row = self._s.get(OnboardingStatusTable, user_id)
        return _status_from_row(row) if row else None

    def set_state(self, user_id: str, state: OnboardingState) -> OnboardingStatus:
        row = self._s.get(OnboardingStatusTable, user_id)
        now = utc_now()
        if row is None:
            row = OnboardingStatusTable(
                owner_id=user_id, state=state.value, prompted_at=now, updated_at=now
            )
            self._s.add(row)
        else:
            row.state = state.value
            row.updated_at = now
        self._s.flush()
        return _status_from_row(row)
