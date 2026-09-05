from datetime import datetime
from typing import List, Optional
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Recipe(Base):
    """
    Esya Crafting Tarifi Modeli
    """
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    result_item_id: Mapped[str] = mapped_column(String(128), ForeignKey("items.id"), index=True)
    result_quantity: Mapped[int] = mapped_column(Integer, default=1)
    recipe_type: Mapped[str] = mapped_column(String(32), default="crafting")
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Iliskiler
    result_item: Mapped["Item"] = relationship("Item", back_populates="recipes_created")
    ingredients: Mapped[List["RecipeIngredient"]] = relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Recipe id={self.id} result={self.result_item_id} qty={self.result_quantity}>"


class RecipeIngredient(Base):
    """
    Tarif Bilesenleri Modeli
    """
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(128), ForeignKey("items.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    slot_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Iliskiler
    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")

    def __repr__(self) -> str:
        return f"<RecipeIngredient item={self.item_id} qty={self.quantity}>"
