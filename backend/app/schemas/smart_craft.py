from typing import List, Optional
from pydantic import BaseModel, Field


class SmartCraftStep(BaseModel):
    step_number: int
    action_type: str = Field(..., description="BUY_BAZAAR, INSTA_BUY_BAZAAR, BUY_AH, CRAFT, SELL_AH, SELL_BAZAAR, INSTA_SELL_BAZAAR")
    item_name: str
    item_id: Optional[str] = None
    quantity: int
    unit_price: float
    total_price: float
    note: Optional[str] = None


class SmartCraftFlipItem(BaseModel):
    result_item_id: str
    result_name: str
    tier: Optional[str] = None
    category: Optional[str] = None
    target_market: str = Field(..., description="AUCTION_HOUSE veya BAZAAR")
    buy_mode: str = Field("buy_order", description="Hammadde alim modu: buy_order veya insta_buy")
    bazaar_sell_mode: str = Field("sell_offer", description="Bazaar satis modu: sell_offer veya insta_sell")

    optimal_cost: float = Field(..., description="Akilli secimlerle minimize edilmis toplam maliyet")
    sell_price: float = Field(..., description="Satis fiyati")
    net_revenue: float = Field(..., description="Vergi sonrasi net gelir")
    net_profit: float = Field(..., description="Net kar")
    margin_percent: float = Field(..., description="Yatirim getirisi (ROI %)")
    savings: float = Field(0.0, description="Hazir satin al / craftla optimizasyonundan saglanan tasarruf")

    hourly_volume: int = Field(0, description="Tahmini saatlik pazar satis hacmi")
    profit_per_hour: float = Field(0.0, description="Saatlik tahmini kar")

    # 24s ve 7g Satis Analizi
    avg_price_24h: Optional[float] = Field(None, description="Son 24 saatteki ortalama gercek satis fiyati")
    volume_24h: int = Field(0, description="Son 24 saatte gerceklesen toplam satis adedi")
    avg_price_7d: Optional[float] = Field(None, description="Son 7 gunluk ortalama satis fiyati")
    volume_7d: int = Field(0, description="Son 7 gunde gerceklesen toplam satis adedi")
    liquidity_status: str = Field("ORTA", description="Likidite Durumu (YUKSEK, ORTA, RISKLI)")
    risk_warning: Optional[str] = Field(None, description="Risk veya dikkat uyarisi")

    steps: List[SmartCraftStep] = Field(..., description="Oyuncunun takip edecegi sira ile yapilis rehberi")

