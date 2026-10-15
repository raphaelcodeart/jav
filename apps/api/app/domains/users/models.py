import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        # Il nome utente degli atleti senza email (club/athlete_access.py),
        # minuscolo, unico nell'organizzazione.
        Index("uq_users_org_username", "organization_id", "username", unique=True,
              postgresql_where=text("username IS NOT NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: Il club a cui l'account appartiene: genitori, segreteria e istruttori
    #: di un club. NULL per lo staff della piattaforma (superadmin, chi
    #: gestisce lo Shop), che entra nei club scegliendoli (club/scope.py).
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubs.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    #: Il nome utente di un account atleta ("tiago.lagos"): si entra con
    #: questo o con l'email. Un atleta senza email ha un indirizzo finto
    #: `<username>@atleta.invalid` (.invalid non esiste per definizione, e
    #: core/email.py non ci spedisce niente).
    username: Mapped[str | None] = mapped_column(String(40), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # ACTIVE / FROZEN (an admin-frozen account: login is
    # refused and every existing session revoked immediately, but the row and
    # all its data/history stay exactly as they were, see
    # users/service.py::freeze_user/unfreeze_user and auth/service.py's
    # authenticate() status check).
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    # Set once, at self-registration, when the (now-mandatory) privacy
    # checkbox is accepted -- see auth/service.py::register_with_referral.
    # NULL for every account that predates this field (accounts created by
    # an admin directly) -- there is
    # no retroactive consent to backfill for those, so this column simply
    # stays NULL for them rather than being defaulted to "accepted".
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Profile-completion gate: every account, existing or
    # new, must have all of these filled before using the dashboard -- see
    # users/service.py::is_profile_complete(). Deliberately on User, not
    # Customer/AgentProfile, since a promoter has no Customer row and this
    # is inherently user-level identity data, independent of role.
    fiscal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    residence_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    residence_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    residence_province: Mapped[str | None] = mapped_column(String(2), nullable=True)
    residence_postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residence_country: Mapped[str] = mapped_column(String(2), default="IT")
