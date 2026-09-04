from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Numeric, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Item(Base):
    """
    Hypixel Skyblock Esya Modeli
    Oyundaki tum esyalarin ana kaydini tutar.
    """
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True) # Orn: ENCHANTED_LAVA_BUCKET
    name: Mapped[str] = mapped_column(String(256), index=True)                 # Orn: Enchanted Lava Bucket
    material: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)     # COMMON, RARE, EPIC vb.
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True) # SWORD, ARMOR, MINING vb.
    npc_sell_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True) # NPC Satis Fiyati
    is_bazaar_item: Mapped[bool] = mapped_column(Boolean, default=False)
    icon_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Iliskiler
    recipes_created: Mapped[List["Recipe"]] = relationship("Recipe", back_populates="result_item")
    bazaar_snapshot: Mapped[Optional["BazaarSnapshot"]] = relationship("BazaarSnapshot", back_populates="item", uselist=False)

    def __repr__(self) -> str:
        return f"<Item id={self.id} name={self.name}>"
