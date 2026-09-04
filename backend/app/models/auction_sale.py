from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Numeric, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AHSale(Base):
    """
    Auction House Gerceklesmis Satis Kaydi
    Hypixel /skyblock/auctions_ended endpoint'inden toplanan gercek satislar.
    """
    __tablename__ = "ah_sales"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    auction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    item_id: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    item_name: Mapped[str] = mapped_column(String(256), index=True)
    price: Mapped[float] = mapped_column(Numeric(18, 2))
    bin: Mapped[bool] = mapped_column(Boolean, default=True)
    buyer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    seller: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    def __repr__(self) -> str:
        return f"<AHSale item={self.item_name} price={self.price}>"
