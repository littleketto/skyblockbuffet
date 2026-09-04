from datetime import datetime
from sqlalchemy import Integer, BigInteger, Numeric, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BazaarSnapshot(Base):
    """
    Bazaar Anlik Fiyat ve Hacim Tablosu
    Her urun icin en son piyasa verisini saklar.
    """
    __tablename__ = "bazaar_snapshots"

    item_id: Mapped[str] = mapped_column(String(128), ForeignKey("items.id"), primary_key=True)

    buy_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)   # Insta-Buy (En ucuz Sell Offer)
    sell_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0)  # Insta-Sell (En yuksek Buy Order)

    buy_volume: Mapped[int] = mapped_column(BigInteger, default=0)
    sell_volume: Mapped[int] = mapped_column(BigInteger, default=0)

    buy_orders: Mapped[int] = mapped_column(Integer, default=0)
    sell_orders: Mapped[int] = mapped_column(Integer, default=0)

    buy_moving_week: Mapped[int] = mapped_column(BigInteger, default=0)
    sell_moving_week: Mapped[int] = mapped_column(BigInteger, default=0)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Iliskiler
    item: Mapped["Item"] = relationship("Item", back_populates="bazaar_snapshot")

    def __repr__(self) -> str:
        return f"<BazaarSnapshot item={self.item_id} buy={self.buy_price} sell={self.sell_price}>"
