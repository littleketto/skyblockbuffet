from datetime import datetime
from sqlalchemy import Integer, BigInteger, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BazaarSnapshot(Base):
    """
    Bazaar Anlik Fiyat ve Hacim Kaydi
    Hypixel Bazaar'dan her veri cekildiginde olusan piyasa fotografi.
    """
    __tablename__ = "bazaar_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id"), index=True)

    # Fiyatlar
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)   # Insta-Buy (En ucuz Sell Offer)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)  # Insta-Sell (En yuksek Buy Order)

    # Islem Hacimleri (Volume)
    buy_volume: Mapped[int] = mapped_column(BigInteger, default=0)   # Aninda satin alinan adet
    sell_volume: Mapped[int] = mapped_column(BigInteger, default=0)  # Aninda satilan adet

    # Derinlik (Order Book)
    buy_orders: Mapped[int] = mapped_column(Integer, default=0)   # Bekleyen alis emir adedi
    sell_orders: Mapped[int] = mapped_column(Integer, default=0)  # Bekleyen satis emir adedi

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Iliskiler
    item: Mapped["Item"] = relationship("Item", back_populates="bazaar_snapshots")

    def __repr__(self) -> str:
        return f"<BazaarSnapshot item={self.item_id} buy={self.buy_price} sell={self.sell_price}>"
