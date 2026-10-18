"""Un treinador, più club (club/staff_clubs.py): le appartenenze
(`club_staff_memberships`: ACTIVE, o REQUESTED dalla segreteria in attesa del
superadmin), una per ogni istruttore nel suo club di oggi; e la foto del
profilo degli account (`users.photo_url`) per il saluto dell'area del
treinador.

Revision ID: 0041
Revises: 0040
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0041'
down_revision: str | None = '0040'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('photo_url', sa.String(length=500), nullable=True))
    op.create_table('club_staff_memberships',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('club_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='ACTIVE', nullable=False),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('decided_by_user_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'REQUESTED')", name=op.f('ck_club_staff_memberships_status')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name=op.f('fk_club_staff_memberships_club_id_clubs')),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], name=op.f('fk_club_staff_memberships_decided_by_user_id_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_club_staff_memberships_organization_id_organizations')),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_club_staff_memberships_requested_by_user_id_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_club_staff_memberships_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_club_staff_memberships')),
    sa.UniqueConstraint('club_id', 'user_id', name='uq_club_staff_memberships_club_user')
    )
    op.create_index(op.f('ix_club_staff_memberships_club_id'), 'club_staff_memberships', ['club_id'], unique=False)
    op.create_index(op.f('ix_club_staff_memberships_user_id'), 'club_staff_memberships', ['user_id'], unique=False)
    # Ogni istruttore di oggi resta treinador del suo club.
    op.execute("""
        INSERT INTO club_staff_memberships (id, organization_id, club_id, user_id, status, decided_at, created_at)
        SELECT DISTINCT ON (u.id) gen_random_uuid(), u.organization_id, u.club_id, u.id, 'ACTIVE', now(), now()
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE r.code = 'INSTRUCTOR' AND u.club_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table('club_staff_memberships')
    op.drop_column('users', 'photo_url')
