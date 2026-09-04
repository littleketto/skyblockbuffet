from typing import List, Optional
from pydantic import BaseModel, Field


class SmartCraftStep(BaseModel):
    step_number: int
    action_type: str = Field(..., description="BUY_BAZAAR, BUY_AH, CRAFT, SELL_AH, SELL_BAZAAR")
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

    optimal_cost: float = Field(..., description="Akilli secimlerle minimize edilmis toplam maliyet")
    sell_price: float = Field(..., description="Satis fiyati")
    net_revenue: float = Field(..., description="Vergi sonrasi net gelir")
    net_profit: float = Field(..., description="Net kar")
    margin_percent: float = Field(..., description="Yatirim getirisi (ROI %)")
    savings: float = Field(0.0, description="Hazir satin al / craftla optimizasyonundan saglanan tasarruf")

    hourly_volume: int = Field(0, description="Tahmini saatlik pazar satis hacmi")
    profit_per_hour: float = Field(0.0, description="Saatlik tahmini kar")

    steps: List[SmartCraftStep] = Field(..., description="Oyuncunun takip edecegi sira ile yapilis rehberi")
