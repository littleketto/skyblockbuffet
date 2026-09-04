from typing import Optional
from pydantic import BaseModel, Field


class AHFlipItem(BaseModel):
    item_name: str = Field(..., description="Esya Adi")
    item_id: Optional[str] = Field(None, description="Esyanin Hypixel ID'si")
    tier: Optional[str] = None
    category: Optional[str] = None

    lowest_bin: float = Field(..., description="En ucuz BIN (Alis Fiyatimiz - LBIN)")
    second_lowest_bin: float = Field(..., description="Ikinci en ucuz BIN fiyati")
    target_sell_price: float = Field(..., description="Tavsiye edilen satis fiyati")
    net_profit: float = Field(..., description="AH vergisi dusulmus net kar")
    margin_percent: float = Field(..., description="Kar yuzdesi (ROI %)")

    total_listings: int = Field(..., description="Pazardaki toplam aktif ilan sayisi")
    auction_uuid: str = Field(..., description="Oyunda /viewauction <uuid> ile alinacak ilan ID'si")

    # Gecmis Satis ve Likidite Analizi (Coflnet & Tarihsel DB)
    daily_volume: int = Field(0, description="Son 24 saatte gerceklesen toplam satis adedi")
    avg_sold_price: Optional[float] = Field(None, description="Son 24 saatteki gercek ortalama satis fiyati")
    liquidity_status: str = Field("ORTA", description="Likidite Durumu (YUKSEK, ORTA, RISKLI)")
    risk_warning: Optional[str] = Field(None, description="Risk veya dikkat uyarisi")
