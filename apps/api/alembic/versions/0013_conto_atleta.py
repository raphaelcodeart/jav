"""Il conto dell'atleta: ogni atleta può avere il suo accesso.

- `users.username`: si entra con l'email **o** con un nome utente (i figli
  senza email). Unico nell'organizzazione, solo dove c'è.
- `club_athletes.user_id`: l'account con cui l'atleta entra nella sua area
  (ruolo ATHLETE); vuoto finché il titolare non glielo crea. Per un atleta
  "me stesso" è il titolare.
- `club_athlete_login_codes`: i QR per entrare al volo (solo l'impronta del
  codice, revocabili, con scadenza).

Il ruolo ATHLETE e il permesso club.athlete sono dati: li crea
`python -m app.seed.bootstrap` (idempotente). Gli atleti "me stesso" che già
esistono ricevono qui il loro user_id (= il titolare): l'area atleta di un
adulto è la sua. Regole in docs/club-portal.md, "Il conto dell'atleta".

Revision ID: 0013
Revises: 0012
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=40), nullable=True))
    op.create_index(
        'uq_users_org_username', 'users', ['organization_id', 'username'], unique=True,
        postgresql_where=sa.text('username IS NOT NULL'),
    )

    op.add_column('club_athletes', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_club_athletes_user_id_users'), 'club_athletes', 'users', ['user_id'], ['id'])
    op.create_unique_constraint(op.f('uq_club_athletes_user_id'), 'club_athletes', ['user_id'])
    op.execute("UPDATE club_athletes SET user_id = guardian_user_id WHERE is_self")

    op.create_table('club_athlete_login_codes',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('athlete_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['club_athletes.id'], name=op.f('fk_club_athlete_login_codes_athlete_id_club_athletes')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_club_athlete_login_codes_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_athlete_login_codes_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_athlete_login_codes')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_club_athlete_login_codes_token_hash')),
    )
    op.create_index(op.f('ix_club_athlete_login_codes_athlete_id'), 'club_athlete_login_codes', ['athlete_id'], unique=False)
    op.create_index(op.f('ix_club_athlete_login_codes_organization_id'), 'club_athlete_login_codes', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_club_athlete_login_codes_organization_id'), table_name='club_athlete_login_codes')
    op.drop_index(op.f('ix_club_athlete_login_codes_athlete_id'), table_name='club_athlete_login_codes')
    op.drop_table('club_athlete_login_codes')
    op.drop_constraint(op.f('uq_club_athletes_user_id'), 'club_athletes', type_='unique')
    op.drop_constraint(op.f('fk_club_athletes_user_id_users'), 'club_athletes', type_='foreignkey')
    op.drop_column('club_athletes', 'user_id')
    op.drop_index('uq_users_org_username', table_name='users')
    op.drop_column('users', 'username')
