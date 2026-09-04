import math
from typing import List, Optional, Dict
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import Item
from app.models.recipe import Recipe, RecipeIngredient
from app.models.bazaar import BazaarSnapshot
from app.schemas.craft import CraftFlipItem, CraftIngredientDetail


async def calculate_craft_flips(
    db: AsyncSession,
    min_profit: float = 1000.0,
    min_hourly_volume: int = 5,
    max_budget: Optional[float] = None,
    tax_rate: Optional[float] = None,
    market_share_alpha: float = 0.10,
    limit: int = 100,
) -> List[CraftFlipItem]:
    """
    Craft Flipping Firsatlarini Hesaplar:
    1. Her tarifin bilesenlerini (ingredients) Bazaar'dan alis emri (Buy Order) ile alma maliyetini hesaplar.
    2. Uretilen nihai esyanin Bazaar satis fiyati ve vergi dusulmus net gelirini bulur.
    3. Net Kar = Net Gelir - Toplam Hammadde Maliyeti
    4. PPH (Profit Per Hour - Saatlik Uretim Kari) projeksiyonu cikarir.
    """
    tax = tax_rate if tax_rate is not None else settings.BAZAAR_TAX_RATE

    # 1. Tum Bazaar Snapshotlarini tek seferde cekip sozluk yap
    bazaar_res = await db.execute(select(BazaarSnapshot))
    bazaar_dict: Dict[str, BazaarSnapshot] = {b.item_id: b for b in bazaar_res.scalars().all()}

    # 2. Tum Item bilgilerini tek seferde cekip sozluk yap
    items_res = await db.execute(select(Item))
    items_dict: Dict[str, Item] = {it.id: it for it in items_res.scalars().all()}

    # 3. Tum aktif tarifleri bilesenleriyle birlikte tek sorguda cek (selectinload)
    recipes_res = await db.execute(
        select(Recipe).where(Recipe.is_active == True).options(selectinload(Recipe.ingredients))
    )
    recipes = recipes_res.scalars().all()

    flips: List[CraftFlipItem] = []

    for r in recipes:
        result_item = items_dict.get(r.result_item_id)
        result_snap = bazaar_dict.get(r.result_item_id)

        # Eger uretilen esya Bazaar'da yoksa veya fiyati olusmamissa atla
        if not result_snap or float(result_snap.buy_price) <= 0.1:
            continue

        # Hammadde maliyetini hesapla
        total_material_cost = 0.0
        ingredients_detail: List[CraftIngredientDetail] = []
        is_craftable = True

        for ing in r.ingredients:
            ing_snap = bazaar_dict.get(ing.item_id)
            ing_item = items_dict.get(ing.item_id)
            ing_name = ing_item.name if ing_item else ing.item_id.replace("_", " ").title()

            # Hammaddeyi Buy Order (sell_price) ile aliriz
            if ing_snap and float(ing_snap.sell_price) > 0:
                unit_cost = float(ing_snap.sell_price)
            elif ing_item and ing_item.npc_sell_price:
                unit_cost = float(ing_item.npc_sell_price)
            else:
                # Fiyati bilinmeyen ozel bir hammadde varsa bu tarifi simdilik atla
                is_craftable = False
                break

            total_cost = unit_cost * ing.quantity
            total_material_cost += total_cost

            ingredients_detail.append(
                CraftIngredientDetail(
                    item_id=ing.item_id,
                    name=ing_name,
                    quantity=ing.quantity,
                    unit_cost=round(unit_cost, 2),
                    total_cost=round(total_cost, 2),
                )
            )

        if not is_craftable or total_material_cost <= 0:
            continue

        # Butce filtresi
        if max_budget is not None and total_material_cost > max_budget:
            continue

        # Satis Geliri ve Net Kar
        sell_unit_price = float(result_snap.buy_price)
        gross_revenue = sell_unit_price * r.result_quantity
        net_revenue = gross_revenue * (1.0 - tax)
        profit = net_revenue - total_material_cost

        if profit < min_profit:
            continue

        margin_percent = (profit / total_material_cost) * 100.0

        # Saatlik Hacim ve Uretim Hizi
        hourly_volume = int(result_snap.sell_moving_week / 168)
        if hourly_volume < min_hourly_volume:
            continue

        # Bir oyuncu saatte kac adet uretebilir veya pazara eritebilir?
        fillable_per_hour = min(120.0, max(1.0, float(hourly_volume) * market_share_alpha))
        profit_per_hour = profit * fillable_per_hour

        ranking_score = profit_per_hour * math.log10(max(10, hourly_volume))

        flips.append(
            CraftFlipItem(
                recipe_id=r.id,
                result_item_id=r.result_item_id,
                result_name=result_item.name if result_item else r.result_item_id.replace("_", " ").title(),
                result_quantity=r.result_quantity,
                tier=result_item.tier if result_item else None,
                category=result_item.category if result_item else None,
                material_cost=round(total_material_cost, 2),
                sell_price=round(sell_unit_price, 2),
                net_revenue=round(net_revenue, 2),
                profit=round(profit, 2),
                margin_percent=round(margin_percent, 2),
                hourly_volume=hourly_volume,
                profit_per_hour=round(profit_per_hour, 2),
                ranking_score=round(ranking_score, 2),
                ingredients=ingredients_detail,
            )
        )

    flips.sort(key=lambda x: x.profit_per_hour, reverse=True)
    return flips[:limit]
