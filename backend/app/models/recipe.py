from typing import List, Optional
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Recipe(Base):
    """
    Esya Crafting Tarifi Modeli
    Hangi esyanin kac adet uretildigini ve tarif tipini tutar.
    """
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    result_item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id"), index=True)
    result_quantity: Mapped[int] = mapped_column(Integer, default=1)
    recipe_type: Mapped[str] = mapped_column(String, default="CRAFTING_TABLE") # CRAFTING_TABLE, FORGE vb.

    # Iliskiler
    result_item: Mapped["Item"] = relationship("Item", back_populates="recipes_created")
    ingredients: Mapped[List["RecipeIngredient"]] = relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Recipe result={self.result_item_id} qty={self.result_quantity}>"


class RecipeIngredient(Base):
    """
    Tarif Bilesenleri Modeli
    Bir tarifin uretilmesi icin gereken hammaddeleri ve adetlerini tutar.
    """
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String, index=True) # Hammadde esya ID'si
    count: Mapped[int] = mapped_column(Integer, default=1)   # Kac adet gerekiyor?
    slot: Mapped[Optional[str]] = mapped_column(String, nullable=True) # A1, A2, B1 vb. grid yeri

    # Iliskiler
    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")

    def __repr__(self) -> str:
        return f"<RecipeIngredient item={self.item_id} count={self.count}>"
