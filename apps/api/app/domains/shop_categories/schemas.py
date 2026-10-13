import uuid

from pydantic import BaseModel, Field


class ShopCategoryRead(BaseModel):
    id: uuid.UUID
    shop: str
    name: str
    position: int
    active: bool
    #: How many products carry this category, counted in the same query that
    #: reads the list -- the admin screen shows it next to every chip.
    product_count: int = 0


class ShopCategoryCreate(BaseModel):
    shop: str
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(default=0, ge=0, le=9999)


class ShopCategoryUpdate(BaseModel):
    """Only the fields sent are changed: renaming a category never resets
    its position, and switching it off never renames it."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None


class ShopCategoryAssignmentUpdate(BaseModel):
    """The categories of ONE product inside ONE shop, in full: what is sent
    is what the product ends up with, and an empty list removes them all."""

    shop: str
    product_id: uuid.UUID
    category_ids: list[uuid.UUID] = []


class ShopCategoryAssignmentRead(BaseModel):
    shop: str
    product_id: uuid.UUID
    category_ids: list[uuid.UUID]
