from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.craft import CraftFlipItem
from app.schemas.smart_craft import SmartCraftFlipItem
from app.services.craft_flipper import calculate_craft_flips
from app.services.smart_craft_engine import smart_craft_engine

router = APIRouter(prefix="/craft", tags=["Crafting"])


@router.get("/flips", response_model=List[CraftFlipItem])
async def get_craft_flips(
    min_profit: float = Query(2000.0, description="Minimum craft basi net kar"),
    min_hourly_volume: int = Query(5, description="Uretilen esyanin minimum saatlik pazar satis hacmi"),
    max_budget: Optional[float] = Query(None, description="Maksimum hammadde maliyeti (coins)"),
    limit: int = Query(100, ge=1, le=500, description="Listelenecek maksimum firsat sayisi"),
    db: AsyncSession = Depends(get_db),
):
    """Standart Bazaar-to-Bazaar Crafting Firsatlarini Listeler."""
    return await calculate_craft_flips(
        db=db,
        min_profit=min_profit,
        min_hourly_volume=min_hourly_volume,
        max_budget=max_budget,
        limit=limit,
    )


@router.get("/smart-flips", response_model=List[SmartCraftFlipItem])
async def get_smart_craft_flips(
    market: str = Query("all", description="all, ah veya bazaar"),
    buy_mode: str = Query("buy_order", description="buy_order veya insta_buy"),
    bazaar_sell_mode: str = Query("sell_offer", description="sell_offer veya insta_sell"),
    min_profit: float = Query(0.0, description="Minimum net kar (coins)"),
    min_margin: float = Query(0.0, description="Minimum kar marji (ROI %)"),
    max_budget: Optional[float] = Query(None, description="Maksimum butce (coins)"),
    limit: int = Query(3000, ge=1, le=10000, description="Listelenecek firsat sayisi"),
    db: AsyncSession = Depends(get_db),
):
    """
    Akilli Cok Asamali Craft Flipping & AH Entegrasyonu:
    Bazaar'dan alip AH'de satma, cok kademeli esyalarda 'Buy vs Craft' optimizasyonu
    ve sira ile adim adim yapilis rehberini dondurur.
    buy_mode: 'buy_order' (Siparis acarak alma) veya 'insta_buy' (Aninda satin alarak craftlama)
    bazaar_sell_mode: 'sell_offer' (Bazaar'a siparis acarak satis) veya 'insta_sell' (Bazaar'a aninda bozdurarak satis)
    """
    return await smart_craft_engine.calculate_smart_flips(
        db=db,
        market_filter=market,
        buy_mode=buy_mode,
        bazaar_sell_mode=bazaar_sell_mode,
        min_profit=min_profit,
        min_margin=min_margin,
        max_budget=max_budget,
        limit=limit,
    )
