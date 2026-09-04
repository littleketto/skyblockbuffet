from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.craft import CraftFlipItem
from app.services.craft_flipper import calculate_craft_flips

router = APIRouter(prefix="/craft", tags=["Crafting"])


@router.get("/flips", response_model=List[CraftFlipItem])
async def get_craft_flips(
    min_profit: float = Query(2000.0, description="Minimum craft basi net kar"),
    min_hourly_volume: int = Query(5, description="Uretilen esyanin minimum saatlik pazar satis hacmi"),
    max_budget: Optional[float] = Query(None, description="Maksimum hammadde maliyeti (coins)"),
    limit: int = Query(100, ge=1, le=500, description="Listelenecek maksimum firsat sayisi"),
    db: AsyncSession = Depends(get_db),
):
    """
    Craft Flipping Firsatlarini Listeler:
    Bazaar'dan hammaddeleri alip uretim yaparak en cok kazandiran esyalari ve tarif detaylarini dondurur.
    """
    return await calculate_craft_flips(
        db=db,
        min_profit=min_profit,
        min_hourly_volume=min_hourly_volume,
        max_budget=max_budget,
        limit=limit,
    )
