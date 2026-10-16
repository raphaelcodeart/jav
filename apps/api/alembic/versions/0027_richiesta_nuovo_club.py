"""«Crea il tuo club»: la richiesta arriva come messaggio di contatto con
l'argomento NEW_CLUB (`contact_messages.topic`, club/contact.py).

Revision ID: 0027
Revises: 0026
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0027'
down_revision: str | None = '0026'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_contact_messages_topic'), 'contact_messages', type_='check')
    op.create_check_constraint(
        op.f('ck_contact_messages_topic'), 'contact_messages',
        "topic IN ('GENERAL', 'SPONSOR', 'ENROLMENT', 'EVENTS', 'NEW_CLUB', 'OTHER')",
    )


def downgrade() -> None:
    op.execute("UPDATE contact_messages SET topic = 'OTHER' WHERE topic = 'NEW_CLUB'")
    op.drop_constraint(op.f('ck_contact_messages_topic'), 'contact_messages', type_='check')
    op.create_check_constraint(
        op.f('ck_contact_messages_topic'), 'contact_messages',
        "topic IN ('GENERAL', 'SPONSOR', 'ENROLMENT', 'EVENTS', 'OTHER')",
    )
