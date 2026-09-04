from typing import List, Optional
from pydantic import BaseModel, Field


class CraftIngredientDetail(BaseModel):
    item_id: str
    name: str
    quantity: int
    unit_cost: float
    total_cost: float


class CraftFlipItem(BaseModel):
    recipe_id: int
    result_item_id: str
    result_name: str
    result_quantity: int = 1
    tier: Optional[str] = None
    category: Optional[str] = None

    material_cost: float = Field(..., description="Gereken hammaddelerin toplam alis maliyeti")
    sell_price: float = Field(..., description="Uretilen esyanin birim satis fiyati")
    net_revenue: float = Field(..., description="Vergi sonrasi net satis geliri")
    profit: float = Field(..., description="Craft basina net kar")
    margin_percent: float = Field(..., description="Yatirim getirisi (ROI %)")

    hourly_volume: int = Field(..., description="Son urunun saatlik pazar satis hizi")
    profit_per_hour: float = Field(..., description="Saatlik tahmini uretim kari (PPH)")
    ranking_score: float = Field(..., description="Karlilik ve hacim dengeli puan")

    ingredients: List[CraftIngredientDetail] = Field(..., description="Gereken malzemelerin detayli listesi")
