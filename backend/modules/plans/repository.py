"""U16 Plans — persistence for plan assignments and the daily spend rollup (SEC-8).

Mirrors the U15 trends repository idiom: a ``Protocol`` port, the in-memory mock-first
default, and the SQL adapter mapping 1:1 to ``migrations/001_create_plans_tables.sql``.
``user_id`` is a required argument on every user-scoped method so an adapter structurally
cannot return another owner's rows.

Idempotency contract (BR-SB6): ``mark_expiry_noted`` returns True ONLY for the call that
transitions ``expiry_noted_at`` from NULL — the SQL adapter uses a conditional UPDATE so
concurrent resolvers cannot both win, and the caller emits the expiry audit exactly once.
"""

from __future__ import annotations

from datetime import date, datetime
from threading import RLock
from typing import Protocol

from sqlalchemy import Date, DateTime, Float, String, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import PlanAssignment, PlanTier, UserDailySpend, utc_now


class PlanRepository(Protocol):
    # assignments (US-SB2/SB3 — append-only history)
    def add_assignment(self, user_id: str, assignment: PlanAssignment) -> PlanAssignment: ...
    def latest_assignment(self, user_id: str) -> PlanAssignment | None: ...
    def mark_revoked(self, user_id: str, revoked_at: datetime) -> PlanAssignment | None: ...
    def mark_expiry_noted(self, assignment_id: str, noted_at: datetime) -> bool: ...

    # daily spend rollup (BR-SB7 — observation only)
    def add_spend(
        self, user_id: str, day: date, module: str, usd: float, now: datetime
    ) -> UserDailySpend: ...
    def get_spend(self, user_id: str, day: date, module: str) -> UserDailySpend | None: ...

    # durability boundary (trends idiom): the app-shell request scope commits; the in-memory
    # double counts calls so tests can spy the boundary.
    def commit(self) -> None: ...


def _is_active(assignment: PlanAssignment, now: datetime) -> bool:
    """BR-SB2 — active is DERIVED: latest row with ``now < expiresAt``. ``revokedAt`` does
    NOT end the effect (paid-through-period); it only stops a future renewal."""
    return now < assignment.expiresAt


class InMemoryPlanRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._assignments: dict[str, list[PlanAssignment]] = {}
        self._spend: dict[tuple[str, date, str], UserDailySpend] = {}
        self.commits = 0

    def add_assignment(self, user_id: str, assignment: PlanAssignment) -> PlanAssignment:
        with self._lock:
            self._assignments.setdefault(user_id, []).append(assignment)
            return assignment

    def latest_assignment(self, user_id: str) -> PlanAssignment | None:
        with self._lock:
            rows = self._assignments.get(user_id, [])
            if not rows:
                return None
            return max(rows, key=lambda row: (row.startsAt, row.createdAt, row.id))

    def mark_revoked(self, user_id: str, revoked_at: datetime) -> PlanAssignment | None:
        with self._lock:
            latest = self.latest_assignment(user_id)
            if latest is None or latest.revokedAt is not None:
                return None
            if not _is_active(latest, revoked_at):
                return None
            updated = latest.model_copy(update={"revokedAt": revoked_at})
            rows = self._assignments[user_id]
            self._assignments[user_id] = [
                updated if row.id == latest.id else row for row in rows
            ]
            return updated

    def mark_expiry_noted(self, assignment_id: str, noted_at: datetime) -> bool:
        with self._lock:
            for user_id, rows in self._assignments.items():
                for row in rows:
                    if row.id != assignment_id:
                        continue
                    if row.expiryNotedAt is not None:
                        return False  # already noted — idempotent loser (BR-SB6)
                    updated = row.model_copy(update={"expiryNotedAt": noted_at})
                    self._assignments[user_id] = [
                        updated if r.id == assignment_id else r for r in rows
                    ]
                    return True
            return False

    def add_spend(
        self, user_id: str, day: date, module: str, usd: float, now: datetime
    ) -> UserDailySpend:
        with self._lock:
            key = (user_id, day, module)
            current = self._spend.get(key)
            if current is None:
                updated = UserDailySpend(
                    userId=user_id, date=day, module=module, usd=usd, updatedAt=now
                )
            else:
                updated = current.model_copy(
                    update={"usd": current.usd + usd, "updatedAt": now}
                )
            self._spend[key] = updated
            return updated

    def get_spend(self, user_id: str, day: date, module: str) -> UserDailySpend | None:
        with self._lock:
            return self._spend.get((user_id, day, module))

    def commit(self) -> None:
        with self._lock:
            self.commits += 1


class Base(DeclarativeBase):
    pass


class PlanAssignmentTable(Base):
    __tablename__ = "plan_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_by: Mapped[str] = mapped_column(String(36), nullable=False)
    expiry_noted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserDailySpendTable(Base):
    __tablename__ = "user_daily_spend"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    module: Mapped[str] = mapped_column(String(32), primary_key=True)
    usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _assignment_from_row(row: PlanAssignmentTable) -> PlanAssignment:
    return PlanAssignment(
        id=row.id,
        userId=row.user_id,
        tier=PlanTier(row.tier),
        startsAt=row.starts_at,
        expiresAt=row.expires_at,
        revokedAt=row.revoked_at,
        grantedBy=row.granted_by,
        expiryNotedAt=row.expiry_noted_at,
        createdAt=row.created_at,
    )


class SqlPlanRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add_assignment(self, user_id: str, assignment: PlanAssignment) -> PlanAssignment:
        row = PlanAssignmentTable(
            id=assignment.id,
            user_id=user_id,
            tier=assignment.tier.value,
            starts_at=assignment.startsAt,
            expires_at=assignment.expiresAt,
            revoked_at=assignment.revokedAt,
            granted_by=assignment.grantedBy,
            expiry_noted_at=assignment.expiryNotedAt,
            created_at=assignment.createdAt,
        )
        self._s.add(row)
        self._s.flush()
        return _assignment_from_row(row)

    def latest_assignment(self, user_id: str) -> PlanAssignment | None:
        row = self._s.scalars(
            select(PlanAssignmentTable)
            .where(PlanAssignmentTable.user_id == user_id)
            .order_by(
                PlanAssignmentTable.starts_at.desc(),
                PlanAssignmentTable.created_at.desc(),
                PlanAssignmentTable.id.desc(),
            )
            .limit(1)
        ).first()
        return _assignment_from_row(row) if row else None

    def mark_revoked(self, user_id: str, revoked_at: datetime) -> PlanAssignment | None:
        latest = self.latest_assignment(user_id)
        if latest is None or latest.revokedAt is not None:
            return None
        if not _is_active(latest, revoked_at):
            return None
        row = self._s.get(PlanAssignmentTable, latest.id)
        if row is None:  # pragma: no cover — read-your-writes within one session
            return None
        row.revoked_at = revoked_at
        self._s.flush()
        return _assignment_from_row(row)

    def mark_expiry_noted(self, assignment_id: str, noted_at: datetime) -> bool:
        # Conditional UPDATE — only the transition NULL→noted counts, so two concurrent
        # resolvers cannot both claim the one-shot expiry audit (BR-SB6).
        result = self._s.execute(
            update(PlanAssignmentTable)
            .where(
                PlanAssignmentTable.id == assignment_id,
                PlanAssignmentTable.expiry_noted_at.is_(None),
            )
            .values(expiry_noted_at=noted_at)
        )
        self._s.flush()
        return bool(result.rowcount)

    def add_spend(
        self, user_id: str, day: date, module: str, usd: float, now: datetime
    ) -> UserDailySpend:
        row = self._s.get(UserDailySpendTable, (user_id, day, module))
        if row is None:
            row = UserDailySpendTable(
                user_id=user_id, date=day, module=module, usd=usd, updated_at=now
            )
            self._s.add(row)
        else:
            row.usd = row.usd + usd
            row.updated_at = now
        self._s.flush()
        return UserDailySpend(
            userId=row.user_id,
            date=row.date,
            module=row.module,
            usd=row.usd,
            updatedAt=row.updated_at,
        )

    def get_spend(self, user_id: str, day: date, module: str) -> UserDailySpend | None:
        row = self._s.get(UserDailySpendTable, (user_id, day, module))
        if row is None:
            return None
        return UserDailySpend(
            userId=row.user_id,
            date=row.date,
            module=row.module,
            usd=row.usd,
            updatedAt=row.updated_at,
        )

    def commit(self) -> None:
        self._s.commit()


__all__ = [
    "InMemoryPlanRepository",
    "PlanRepository",
    "SqlPlanRepository",
    "utc_now",
]
