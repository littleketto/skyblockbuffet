from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.bazaar import BazaarFlipItem
from app.services.bazaar_flipper import calculate_bazaar_flips

router = APIRouter(prefix="/bazaar", tags=["Bazaar"])


@router.get("/flips", response_model=List[BazaarFlipItem])
async def get_bazaar_flips(
    min_profit: float = Query(1000.0, description="Minimum net kar (adet basi)"),
    min_hourly_volume: int = Query(10, description="Minimum saatlik pazar hacmi"),
    max_budget: Optional[float] = Query(None, description="Maksimum alis butcesi (coins)"),
    limit: int = Query(100, ge=1, le=500, description="Listelenecek maksimum firsat sayisi"),
    db: AsyncSession = Depends(get_db),
):
    """
    Bazaar Flipping Firsatlarini Listeler:
    En yuksek PPH (saatlik kar) ve getiri oranina sahip urunleri siralar.
    """
    return await calculate_bazaar_flips(
        db=db,
        min_profit=min_profit,
        min_hourly_volume=min_hourly_volume,
        max_budget=max_budget,
        limit=limit,
    )
