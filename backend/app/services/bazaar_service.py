import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.bazaar import BazaarSnapshot
from app.services.hypixel_client import hypixel_client

_last_sync_time: Optional[float] = None
_sync_lock = asyncio.Lock()


async def sync_bazaar_to_db(db: AsyncSession, chunk_size: int = 500) -> int:
    """
    Hypixel Bazaar API'sinden tum urunlerin anlik fiyat, emir ve hacim
    verilerini ceker ve 'bazaar_snapshots' tablosuna kaydeder/gunceller.
    - Buy Order fiyati icin sell_summary[0] (en yuksek aktif alis emri) kullanilir.
    - Sell Offer fiyati icin buy_summary[0] (en dusuk aktif satis emri) kullanilir.
    Boylece oyuncunun oyun icinde gordugu anlik tahta ile 1e1 eslesir.
    """
    global _last_sync_time
    bazaar_data = await hypixel_client.get_bazaar()
    products: Dict[str, Any] = bazaar_data.get("products", {})

    if not products:
        print("Uyari: Bazaar urun verisi bos dondu!")
        return 0

    records = []
    now = datetime.now(timezone.utc)

    for item_id, data in products.items():
        qs = data.get("quick_status", {})
        if not qs:
            continue

        # En iyi Alis Emri (Buy Order - sell_summary icindeki en yuksek aktif alis teklifi)
        sell_summary = data.get("sell_summary", [])
        if sell_summary and len(sell_summary) > 0 and float(sell_summary[0].get("pricePerUnit", 0.0)) > 0:
            best_buy_order = float(sell_summary[0]["pricePerUnit"])
        else:
            best_buy_order = float(qs.get("sellPrice", 0.0))

        # En iyi Satis Emri (Sell Offer - buy_summary icindeki en ucuz aktif satis teklifi)
        buy_summary = data.get("buy_summary", [])
        if buy_summary and len(buy_summary) > 0 and float(buy_summary[0].get("pricePerUnit", 0.0)) > 0:
            best_sell_offer = float(buy_summary[0]["pricePerUnit"])
        else:
            best_sell_offer = float(qs.get("buyPrice", 0.0))

        records.append({
            "item_id": item_id,
            "buy_price": best_sell_offer,  # Insta-Buy fiyati (en ucuz aktif Sell Offer)
            "sell_price": best_buy_order,  # Insta-Sell fiyati (en yuksek aktif Buy Order)
            "buy_volume": int(qs.get("buyVolume", 0)),
            "sell_volume": int(qs.get("sellVolume", 0)),
            "buy_orders": int(qs.get("buyOrders", 0)),
            "sell_orders": int(qs.get("sellOrders", 0)),
            "buy_moving_week": int(qs.get("buyMovingWeek", 0)),
            "sell_moving_week": int(qs.get("sellMovingWeek", 0)),
            "fetched_at": now,
        })

    # Chunking ile veritabanina UPSERT
    total_synced = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        stmt = insert(BazaarSnapshot).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[BazaarSnapshot.item_id],
            set_={
                "buy_price": stmt.excluded.buy_price,
                "sell_price": stmt.excluded.sell_price,
                "buy_volume": stmt.excluded.buy_volume,
                "sell_volume": stmt.excluded.sell_volume,
                "buy_orders": stmt.excluded.buy_orders,
                "sell_orders": stmt.excluded.sell_orders,
                "buy_moving_week": stmt.excluded.buy_moving_week,
                "sell_moving_week": stmt.excluded.sell_moving_week,
                "fetched_at": stmt.excluded.fetched_at,
            }
        )
        await db.execute(stmt)
        total_synced += len(chunk)

    await db.commit()
    _last_sync_time = time.time()
    return total_synced


async def ensure_fresh_bazaar_data(db: AsyncSession, max_age_seconds: float = 15.0) -> None:
    """Eger veritabanindaki Bazaar verisi max_age_seconds'dan eskiyse hemen gunceller."""
    global _last_sync_time
    now = time.time()
    if _last_sync_time is not None and (now - _last_sync_time) < max_age_seconds:
        return

    async with _sync_lock:
        now = time.time()
        if _last_sync_time is not None and (now - _last_sync_time) < max_age_seconds:
            return
        await sync_bazaar_to_db(db)

