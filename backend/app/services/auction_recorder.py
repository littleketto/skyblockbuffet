import re
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.item import Item
from app.models.auction_sale import AHSale
from app.services.hypixel_client import hypixel_client

REFORGES = [
    "Fierce", "Spicy", "Heroic", "Withered", "Necrotic", "Clean", "Fast",
    "Ancient", "Giant", "Loving", "Wise", "Renowned", "Submerged", "Jaded",
    "Hyper", "Grand", "Odd", "Sharp", "Heavy", "Titanic"
]


def extract_base_name(raw_name: str) -> str:
    """Reforge eklerini, yildizlari ve ozel karakterleri kaldirarak saf esya adini bulur."""
    clean = re.sub(r"[\*\✪\§]+", "", raw_name).strip()
    for r in REFORGES:
        if clean.lower().startswith(r.lower() + " "):
            clean = clean[len(r) + 1 :].strip()
            break
    return clean


async def sync_ended_auctions_to_db(db: AsyncSession) -> int:
    """
    Hypixel /skyblock/auctions_ended endpoint'inden son 60 saniyede gerceklesen
    satis verilerini ceker ve PostgreSQL 'ah_sales' tablosuna kaydeder.
    """
    url = f"{hypixel_client.base_url}/skyblock/auctions_ended"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=hypixel_client.headers)
            if res.status_code != 200:
                return 0
            data = res.json()
    except Exception as e:
        print(f"Auctions ended cekme hatasi: {e}")
        return 0

    auctions: List[Dict[str, Any]] = data.get("auctions", [])
    if not auctions:
        return 0

    records = []
    for a in auctions:
        auction_id = a.get("auction_id")
        price = a.get("price", 0)
        timestamp_ms = a.get("timestamp", 0)
        if not auction_id or price <= 0:
            continue

        dt = datetime.utcfromtimestamp(timestamp_ms / 1000.0) if timestamp_ms else datetime.utcnow()

        records.append({
            "auction_id": auction_id,
            "item_id": None, # Ileride NBT'den detayli ID ayrilabilir
            "item_name": a.get("item_name", "Unknown Item"),
            "price": float(price),
            "bin": a.get("bin", True),
            "buyer": a.get("buyer"),
            "seller": a.get("seller"),
            "timestamp": dt,
        })

    if not records:
        return 0

    stmt = insert(AHSale).values(records).on_conflict_do_nothing(index_elements=[AHSale.auction_id])
    await db.execute(stmt)
    await db.commit()
    return len(records)
