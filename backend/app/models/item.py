from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Item(Base):
    """
    Hypixel Skyblock Esya Modeli
    Oyundaki tum esyalarin ana kaydini tutar.
    """
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True) # Orn: ENCHANTED_LAVA_BUCKET
    name: Mapped[str] = mapped_column(String, index=True)                 # Orn: Enchanted Lava Bucket
    tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)     # COMMON, RARE, EPIC vb.
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True) # SWORD, ARMOR, MINING vb.
    npc_sell_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # NPC Satis Fiyati
    is_bazaar: Mapped[bool] = mapped_column(Boolean, default=False, index=True)   # Bazaar'da var mi?

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Iliskiler (Relationships)
    recipes_created: Mapped[List["Recipe"]] = relationship("Recipe", back_populates="result_item")
    bazaar_snapshots: Mapped[List["BazaarSnapshot"]] = relationship("BazaarSnapshot", back_populates="item")

    def __repr__(self) -> str:
        return f"<Item id={self.id} name={self.name}>"
