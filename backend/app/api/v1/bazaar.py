from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.bazaar import BazaarFlipItem
from app.services.bazaar_flipper import calculate_bazaar_flips
from app.services.bazaar_service import ensure_fresh_bazaar_data

router = APIRouter(prefix="/bazaar", tags=["Bazaar"])


@router.get("/flips", response_model=List[BazaarFlipItem])
async def get_bazaar_flips(
    min_profit: float = Query(0.0, description="Minimum net kar (adet basi)"),
    min_hourly_volume: int = Query(0, description="Minimum saatlik pazar hacmi"),
    max_budget: Optional[float] = Query(None, description="Maksimum alis butcesi (coins)"),
    limit: Optional[int] = Query(3000, ge=1, le=10000, description="Listelenecek maksimum firsat sayisi"),
    fresh: bool = Query(False, description="Zorunlu anlik guncelleme"),
    db: AsyncSession = Depends(get_db),
):
    """
    Bazaar Flipping Firsatlarini Listeler:
    En yuksek PPH (saatlik kar) ve getiri oranina sahip urunleri siralar.
    """
    # Eger veri 15 saniyeden eskiyse veya kullanici 'fresh' istediyse aninda guncelle
    max_age = 5.0 if fresh else 15.0
    await ensure_fresh_bazaar_data(db, max_age_seconds=max_age)

    return await calculate_bazaar_flips(
        db=db,
        min_profit=min_profit,
        min_hourly_volume=min_hourly_volume,
        max_budget=max_budget,
        limit=limit,
    )


@router.get("/history/{item_id}")
async def get_bazaar_item_history(item_id: str):
    """
    Belirli bir Bazaar urununun son 24 saat ve son 7 gunluk
    ortalama Insta-Buy ve Insta-Sell fiyat istatistiklerini getirir.
    """
    from app.services.coflnet_service import coflnet_service
    history = await coflnet_service.get_bazaar_history(item_id)
    if not history:
        return {"item_id": item_id, "error": "Geçmiş veri bulunamadı"}
    return history
