from typing import List, Optional
from fastapi import APIRouter, Query

from app.schemas.auction import AHFlipItem
from app.services.auction_service import auction_service

router = APIRouter(prefix="/auction", tags=["Auction House"])


@router.get("/flips", response_model=List[AHFlipItem])
async def get_auction_flips(
    min_profit: float = Query(100000.0, description="Minimum net kar (coins)"),
    min_margin: float = Query(15.0, description="Minimum kar marji (ROI %)"),
    max_budget: Optional[float] = Query(None, description="Maksimum alis butcesi (coins)"),
    limit: int = Query(50, ge=1, le=200, description="Listelenecek maksimum ilan sayisi"),
):
    """
    Auction House Lowest BIN (LBIN) Sniping Firsatlarini Listeler:
    Canli olarak taranan 40.000+ ilan icerisinden piyasa altina konmus esyalari dondurur.
    """
    return await auction_service.calculate_ah_flips(
        min_profit=min_profit,
        min_margin=min_margin,
        max_budget=max_budget,
        limit=limit,
    )
