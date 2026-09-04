from typing import Optional
from pydantic import BaseModel, Field


class AHFlipItem(BaseModel):
    item_name: str = Field(..., description="Eşya Adı")
    tier: Optional[str] = None
    category: Optional[str] = None

    lowest_bin: float = Field(..., description="En ucuz BIN (Alis Fiyatimiz - LBIN)")
    second_lowest_bin: float = Field(..., description="Ikinci en ucuz BIN fiyati")
    target_sell_price: float = Field(..., description="Tavsiye edilen satis fiyati")
    net_profit: float = Field(..., description="AH vergisi dusulmus net kar")
    margin_percent: float = Field(..., description="Kar yuzdesi (ROI %)")

    total_listings: int = Field(..., description="Pazardaki toplam aktif ilan sayisi")
    auction_uuid: str = Field(..., description="Oyunda /viewauction <uuid> ile aninda cekilecek ilan ID'si")
