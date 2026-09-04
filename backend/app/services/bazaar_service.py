from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.bazaar import BazaarSnapshot
from app.services.hypixel_client import hypixel_client


async def sync_bazaar_to_db(db: AsyncSession, chunk_size: int = 500) -> int:
    """
    Hypixel Bazaar API'sinden tum urunlerin anlik fiyat, emir ve hacim
    verilerini ceker ve 'bazaar_snapshots' tablosuna kaydeder/gunceller.
    """
    print("Hypixel API'den Bazaar canli verileri cekiliyor...")
    bazaar_data = await hypixel_client.get_bazaar()
    products: Dict[str, Any] = bazaar_data.get("products", {})

    if not products:
        print("Uyari: Bazaar urun verisi bos dondu!")
        return 0

    records = []
    now = datetime.utcnow()

    for item_id, data in products.items():
        qs = data.get("quick_status", {})
        if not qs:
            continue

        records.append({
            "item_id": item_id,
            "buy_price": float(qs.get("buyPrice", 0.0)),
            "sell_price": float(qs.get("sellPrice", 0.0)),
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
    print(f"Basarili! {total_synced} Bazaar urununun anlik piyasa verisi kaydedildi.")
    return total_synced
