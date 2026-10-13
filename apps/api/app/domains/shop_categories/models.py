"""Le categorie dello Shop (Session 73): a filter the customer sees above
every shop grid, kept as a layer on top of the products instead of a column
inside them.

The Shop sells from six places at once -- the three sections of our own
catalog (`catalog.products`, told apart by `Product.category`) and the three
imported-product shops (`aliexpress_dropshipping`, `cj_dropshipping`,
`shopify_dropshipping`, plus the old hand-made `imported_products` shown
inside the AliExpress tab). Each of them keeps its own product table and
knows nothing about this domain: nothing here writes to those tables, and
dropping these two is enough to remove the whole feature.

That isolation is the reason the categories live in their own table rather
than as a `category_id` column on five different product tables: a fourth
marketplace (see docs/business-rules.md) gains categories by adding a string
to SHOPS, not a migration per shop.

`Product.category` (INTERNAL / PARTNER / DROPSHIPPING) is a different thing
entirely and is left alone: it decides WHICH shop a catalog product belongs
to, while a ShopCategory decides where it sits INSIDE that shop.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: The seven grids a category can belong to. The first three are our own
#: catalog, and are `Product.category` lower-cased (see shop_for_catalog_
#: category below) so the mapping never needs a lookup table; the last three
#: are the marketplaces. The legacy `imported_products` rows have no shop of
#: their own: they are shown inside the AliExpress tab (Marketplace 3), so
#: they are categorised under "aliexpress" like everything else there.
SHOPS = ("internal", "partner", "dropshipping", "aliexpress", "cj", "shopify", "jav_market", "kappa_market", "vaitto_market", "symphonya_market", "soleil_market")

#: The subset served by `catalog.products` -- one product table, three shops.
CATALOG_SHOPS = ("internal", "partner", "dropshipping")


def shop_for_catalog_category(category: str | None) -> str:
    """Which shop a `catalog.products` row belongs to. Deliberately just the
    lower-cased `Product.category`, so the two vocabularies can never drift
    apart -- see PRODUCT_CATEGORIES in catalog/schemas.py."""
    return (category or "INTERNAL").lower()


class ShopCategory(UUIDPKMixin, TimestampMixin, Base):
    """One filter chip in one shop, e.g. "Illuminazione" in Marketplace 1.

    A category belongs to exactly one shop: the same name may exist in two
    shops (an administrator curates each grid separately), but never twice
    in the same one -- hence the unique index on lower(name), which also
    refuses "Casa" next to "casa". The service checks the same thing first,
    so the customer-facing error is Italian rather than an integrity error.
    """

    __tablename__ = "shop_categories"
    __table_args__ = (
        Index(
            "uq_shop_categories_organization_id_shop_name",
            "organization_id",
            "shop",
            text("lower(name)"),
            unique=True,
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    #: One of SHOPS.
    shop: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    #: The order the chips are shown in; ties are broken by name.
    position: Mapped[int] = mapped_column(Integer, default=0)
    #: A category switched off keeps its products (nothing is lost) but is
    #: not offered to the customer as a filter.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopCategoryProduct(UUIDPKMixin, TimestampMixin, Base):
    """A product is in a category. Many to many: a product may carry several
    categories, and a category holds as many products as the administrator
    puts in it.

    `product_id` has **no foreign key**, and that is deliberate: it points at
    a row in one of five different product tables (`products`,
    `imported_products`, `cj_products`, `shopify_products`,
    `aliexpress_products`), which is what `shop` tells apart. This is the one
    place the isolation of this domain costs something -- the database cannot
    enforce that the product exists, so the service always resolves the id
    against the shop it was sent with, and a deleted product simply leaves a
    row here that no list will ever read.
    """

    __tablename__ = "shop_category_products"
    __table_args__ = (
        UniqueConstraint("category_id", "product_id", name="uq_shop_category_products_category_id"),
        #: What every product list asks: "the categories of these ids, in
        #: this shop" -- one query per page, never one per product.
        Index(
            "ix_shop_category_products_organization_id_shop_product_id",
            "organization_id",
            "shop",
            "product_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shop_categories.id", ondelete="CASCADE"), index=True
    )
    #: Repeated from the category so a product list can be answered without
    #: joining shop_categories, and so a stale assignment left behind by a
    #: product that changed shop is never read back into the wrong grid.
    shop: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
