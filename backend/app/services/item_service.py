from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.item import Item
from app.services.hypixel_client import hypixel_client


async def sync_items_to_db(db: AsyncSession, chunk_size: int = 500) -> int:
    """
    Hypixel API'den tum 5.600+ esyayi ve Bazaar urunlerini ceker.
    PostgreSQL'in 32.767 parametre limitine takilmamak icin verileri
    500'erlik parcalar (chunk) halinde yukler.
    """
    print("Hypixel API'den esyalar ve Bazaar verileri cekiliyor...")
    items_data = await hypixel_client.get_items()
    bazaar_data = await hypixel_client.get_bazaar()

    raw_items: List[Dict[str, Any]] = items_data.get("items", [])
    bazaar_product_ids = set(bazaar_data.get("products", {}).keys())

    if not raw_items:
        print("Uyari: Hypixel API'den esya listesi bos dondu!")
        return 0

    records = []
    now = datetime.utcnow()

    for it in raw_items:
        item_id = it.get("id")
        if not item_id:
            continue

        records.append({
            "id": item_id,
            "name": it.get("name", item_id.replace("_", " ").title()),
            "material": it.get("material"),
            "tier": it.get("tier"),
            "category": it.get("category"),
            "npc_sell_price": float(it.get("npc_sell_price")) if it.get("npc_sell_price") is not None else None,
            "is_bazaar_item": item_id in bazaar_product_ids,
            "updated_at": now,
        })

    # Chunking (Parcalayarak yukleme)
    total_synced = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        stmt = insert(Item).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Item.id],
            set_={
                "name": stmt.excluded.name,
                "material": stmt.excluded.material,
                "tier": stmt.excluded.tier,
                "category": stmt.excluded.category,
                "npc_sell_price": stmt.excluded.npc_sell_price,
                "is_bazaar_item": stmt.excluded.is_bazaar_item,
                "updated_at": stmt.excluded.updated_at,
            }
        )
        await db.execute(stmt)
        total_synced += len(chunk)

    await db.commit()
    print(f"Basarili! Toplam {total_synced} esya veritabanina kaydedildi.")
    return total_synced
