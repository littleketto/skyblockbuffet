from typing import List, Optional
from fastapi import APIRouter, Query

from app.schemas.auction import AHFlipItem
from app.services.auction_service import auction_service

router = APIRouter(prefix="/auction", tags=["Auction House"])


@router.get("/flips", response_model=List[AHFlipItem])
async def get_auction_flips(
    min_profit: float = Query(0.0, description="Minimum net kar (coins)"),
    min_margin: float = Query(0.0, description="Minimum kar marji (ROI %)"),
    max_budget: Optional[float] = Query(None, description="Maksimum alis butcesi (coins)"),
    category: Optional[str] = Query(None, description="Kategori (weapons, armor, accessories, consumables, pets, cosmetics, tools_misc)"),
    limit: Optional[int] = Query(6000, ge=1, le=10000, description="Listelenecek maksimum ilan sayisi"),
    fresh: bool = Query(False, description="Zorunlu anlik guncelleme"),
):
    """
    Auction House Lowest BIN (LBIN) Sniping ve Piyasa Listesi:
    Canli olarak taranan 40.000+ aktif ilan icerisinden tum esyalari (5.600+ esya) kapsar.
    """
    return await auction_service.calculate_ah_flips(
        min_profit=min_profit,
        min_margin=min_margin,
        max_budget=max_budget,
        category=category,
        limit=limit,
        fresh=fresh,
    )



@router.get("/history/{item_id}")
async def get_auction_item_history(item_id: str):
    """
    Kullanici herhangi bir AH esyasinin gecmis satislarina veya
    24s hacmine anlik bakmak istediginde tekil olarak sorgular.
    """
    from app.services.coflnet_service import coflnet_service
    history = await coflnet_service.get_item_history_24h(item_id)
    if not history:
        return {"item_id": item_id, "error": "Geçmiş satış verisi bulunamadı", "daily_volume": 0}
    return {"item_id": item_id, **history}
