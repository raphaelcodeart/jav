"""Rinnovo della sessione: richieste simultanee (Session 85).

Una pagina fa più chiamate insieme; scaduto il token d'accesso, ognuna prova
a rinnovare la sessione con lo stesso refresh token. La prima lo ruota, e le
altre venivano rifiutate: «Sessione scaduta» a un utente collegato.
`sessions.replaced_by_session_id` distingue una sessione chiusa da una
rotazione (ha un successore) da una chiusa da un logout (non ce l'ha), così
un token appena ruotato vale ancora per 60 secondi, mai dopo un logout.

Revision ID: d8b3e5f02c46
Revises: c7a2d4e91b35
Create Date: 2026-09-25 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d8b3e5f02c46"
down_revision: Union[str, None] = "c7a2d4e91b35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "replaced_by_session_id", UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", name="fk_sessions_replaced_by_session_id_sessions"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "replaced_by_session_id")
