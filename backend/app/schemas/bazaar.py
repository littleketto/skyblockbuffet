from typing import Optional
from pydantic import BaseModel, Field


class BazaarFlipItem(BaseModel):
    """
    Bazaar Flipping Firsati Modeli
    """
    item_id: str
    name: str
    tier: Optional[str] = None
    category: Optional[str] = None

    buy_price: float = Field(..., description="Alis emri (Buy Order) fiyati - Maliyet")
    sell_price: float = Field(..., description="Satis emri (Sell Offer) fiyati - Brüt Gelir")
    profit_per_item: float = Field(..., description="Vergi dusulmus net kar (adet basi)")
    margin_percent: float = Field(..., description="Yatirim getirisi (ROI %)")

    weekly_buy_volume: int = Field(..., description="Haftalik aninda alis hacmi")
    weekly_sell_volume: int = Field(..., description="Haftalik aninda satis hacmi")
    hourly_volume: int = Field(..., description="Saatlik ortalama pazar hacmi")
    profit_per_hour: float = Field(..., description="Saatlik tahmini net kar (PPH)")
    ranking_score: float = Field(..., description="Likidite ve kar dengesine gore puan")
