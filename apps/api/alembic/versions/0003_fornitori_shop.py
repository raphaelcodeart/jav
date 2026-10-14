"""I fornitori dello Shop e l'email che raccoglie i loro ordini.

- `shop_categories.producer_id`: una categoria dello Shop può avere il suo
  fornitore, ereditato dai prodotti che non ne hanno uno loro;
- `jav_market_settings.supplier_email_from` / `supplier_email_signature`:
  da dove partono le email ai fornitori e con quale firma;
- `jav_market_supplier_dispatches`: ogni email partita verso un fornitore,
  con il testo esatto;
- `jav_market_order_items.producer_id` (il fornitore congelato sulla riga)
  e `supplier_dispatch_id` (l'email con cui la riga è partita; NULL = da
  mandare).

I dati che esistono già: le righe prendono il fornitore del loro prodotto
di oggi (è l'unico che si conosce). Gli ordini già inoltrati prima di questa
migrazione ricevono un invio `LEGACY` per fornitore, così non ricompaiono
nella coda «Fornitori da avvisare» come se nessuno li avesse mai mandati.

Revision ID: 0003
Revises: 0002
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('shop_categories', sa.Column('producer_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_shop_categories_producer_id'), 'shop_categories', ['producer_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_shop_categories_producer_id_jav_market_producers'), 'shop_categories',
        'jav_market_producers', ['producer_id'], ['id'], ondelete='SET NULL',
    )

    op.add_column('jav_market_settings', sa.Column('supplier_email_from', sa.String(length=255), nullable=True))
    op.add_column('jav_market_settings', sa.Column('supplier_email_signature', sa.String(length=1000), nullable=True))

    op.create_table('jav_market_supplier_dispatches',
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('producer_id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('to_email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_by_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source IN ('QUEUE', 'ORDER', 'AUTO', 'LEGACY')", name=op.f('ck_jav_market_supplier_dispatches_source')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_jav_market_supplier_dispatches_organization_id_organizations')),
    sa.ForeignKeyConstraint(['producer_id'], ['jav_market_producers.id'], name=op.f('fk_jav_market_supplier_dispatches_producer_id_jav_market_producers')),
    sa.ForeignKeyConstraint(['sent_by_user_id'], ['users.id'], name=op.f('fk_jav_market_supplier_dispatches_sent_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jav_market_supplier_dispatches'))
    )
    op.create_index(op.f('ix_jav_market_supplier_dispatches_organization_id'), 'jav_market_supplier_dispatches', ['organization_id'], unique=False)
    op.create_index(op.f('ix_jav_market_supplier_dispatches_producer_id'), 'jav_market_supplier_dispatches', ['producer_id'], unique=False)

    op.add_column('jav_market_order_items', sa.Column('producer_id', sa.UUID(), nullable=True))
    op.add_column('jav_market_order_items', sa.Column('supplier_dispatch_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_jav_market_order_items_producer_id'), 'jav_market_order_items', ['producer_id'], unique=False)
    op.create_index(op.f('ix_jav_market_order_items_supplier_dispatch_id'), 'jav_market_order_items', ['supplier_dispatch_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_jav_market_order_items_producer_id_jav_market_producers'), 'jav_market_order_items',
        'jav_market_producers', ['producer_id'], ['id'],
    )
    op.create_foreign_key(
        op.f('fk_jav_market_order_items_supplier_dispatch_id_jav_market_supplier_dispatches'),
        'jav_market_order_items', 'jav_market_supplier_dispatches', ['supplier_dispatch_id'], ['id'],
    )

    # Le righe che esistono già: il fornitore del loro prodotto di oggi.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE jav_market_order_items i SET producer_id = p.producer_id "
        "FROM jav_market_products p WHERE p.id = i.product_id AND i.producer_id IS NULL"
    ))

    # Gli ordini già inoltrati: un invio LEGACY per (ordine, fornitore), con
    # le righe collegate. Il testo vero di quelle email non è mai stato
    # salvato, e qui non lo si inventa.
    groups = bind.execute(sa.text(
        "SELECT o.id, o.organization_id, o.number, o.forwarded_at, o.forwarded_by_user_id, "
        "i.producer_id, coalesce(p.email, '') "
        "FROM jav_market_orders o "
        "JOIN jav_market_order_items i ON i.order_id = o.id "
        "JOIN jav_market_producers p ON p.id = i.producer_id "
        "WHERE o.forwarded_at IS NOT NULL "
        "GROUP BY o.id, o.organization_id, o.number, o.forwarded_at, o.forwarded_by_user_id, i.producer_id, p.email"
    )).all()
    for order_id, org_id, number, forwarded_at, forwarded_by, producer_id, email in groups:
        dispatch_id = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO jav_market_supplier_dispatches (id, created_at, organization_id, producer_id, "
                "source, to_email, subject, body_text, sent_at, sent_by_user_id) "
                "VALUES (:id, now(), :org, :producer, 'LEGACY', :email, :subject, '', :sent_at, :by)"
            ),
            {
                "id": dispatch_id, "org": org_id, "producer": producer_id, "email": email,
                "subject": f"Ordine #{number} (inviato prima dello storico)",
                "sent_at": forwarded_at, "by": forwarded_by,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE jav_market_order_items SET supplier_dispatch_id = :dispatch "
                "WHERE order_id = :order AND producer_id = :producer"
            ),
            {"dispatch": dispatch_id, "order": order_id, "producer": producer_id},
        )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_jav_market_order_items_supplier_dispatch_id_jav_market_supplier_dispatches'),
        'jav_market_order_items', type_='foreignkey',
    )
    op.drop_constraint(
        op.f('fk_jav_market_order_items_producer_id_jav_market_producers'), 'jav_market_order_items',
        type_='foreignkey',
    )
    op.drop_index(op.f('ix_jav_market_order_items_supplier_dispatch_id'), table_name='jav_market_order_items')
    op.drop_index(op.f('ix_jav_market_order_items_producer_id'), table_name='jav_market_order_items')
    op.drop_column('jav_market_order_items', 'supplier_dispatch_id')
    op.drop_column('jav_market_order_items', 'producer_id')
    op.drop_index(op.f('ix_jav_market_supplier_dispatches_producer_id'), table_name='jav_market_supplier_dispatches')
    op.drop_index(op.f('ix_jav_market_supplier_dispatches_organization_id'), table_name='jav_market_supplier_dispatches')
    op.drop_table('jav_market_supplier_dispatches')
    op.drop_column('jav_market_settings', 'supplier_email_signature')
    op.drop_column('jav_market_settings', 'supplier_email_from')
    op.drop_constraint(
        op.f('fk_shop_categories_producer_id_jav_market_producers'), 'shop_categories', type_='foreignkey'
    )
    op.drop_index(op.f('ix_shop_categories_producer_id'), table_name='shop_categories')
    op.drop_column('shop_categories', 'producer_id')
