import re
import asyncio
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import Item
from app.models.recipe import Recipe, RecipeIngredient
from app.models.bazaar import BazaarSnapshot
from app.schemas.smart_craft import SmartCraftFlipItem, SmartCraftStep
from app.services.auction_service import auction_service, clean_minecraft_text, extract_base_item_name


class SmartCraftEngine:
    """
    Akilli Cok Asamali Craft Flipping & AH Entegrasyon Motoru
    - Bazaar'dan hammadde alip AH'de satma fırsatlarını bulur.
    - Ara esyalar icin (Buy vs Craft) karsilastirmasi yaparak en ucuz yolu secer.
    - Adim adim yol haritasi (Action Plan) uretir.
    """

    async def calculate_smart_flips(
        self,
        db: AsyncSession,
        market_filter: str = "all", # "all", "ah", "bazaar"
        min_profit: float = 20000.0,
        min_margin: float = 15.0,
        max_budget: Optional[float] = None,
        limit: int = 50,
    ) -> List[SmartCraftFlipItem]:
        print("Smart Craft Engine: Piyasa verileri ve aktif ilanlar toplaniyor...")

        # 1. Bazaar verilerini yukle
        bazaar_res = await db.execute(select(BazaarSnapshot))
        bazaar_dict: Dict[str, BazaarSnapshot] = {b.item_id: b for b in bazaar_res.scalars().all()}

        # 2. Tum Item bilgilerini yukle
        items_res = await db.execute(select(Item))
        items_list = items_res.scalars().all()
        items_dict: Dict[str, Item] = {it.id: it for it in items_list}

        # 3. Tum tarifleri yukle: { result_item_id: [Recipe] }
        recipes_res = await db.execute(
            select(Recipe).where(Recipe.is_active == True).options(selectinload(Recipe.ingredients))
        )
        recipe_dict: Dict[str, List[Recipe]] = defaultdict(list)
        for r in recipes_res.scalars().all():
            recipe_dict[r.result_item_id].append(r)

        # 4. Auction House aktif BIN ilanlarini topla: { clean_name_lower: (lbin, auction_uuid, tier, category) }
        bin_auctions = await auction_service.fetch_all_bin_auctions(max_concurrent=15)
        ah_lbin_map: Dict[str, Dict[str, Any]] = {}

        for a in bin_auctions:
            raw_name = a.get("item_name", "")
            clean = clean_minecraft_text(raw_name)
            base_name = extract_base_item_name(clean).lower()
            price = float(a.get("starting_bid", 0))
            if price <= 1000:
                continue

            if base_name not in ah_lbin_map or price < ah_lbin_map[base_name]["price"]:
                ah_lbin_map[base_name] = {
                    "price": price,
                    "uuid": a.get("uuid", ""),
                    "tier": a.get("tier"),
                    "category": a.get("category"),
                    "full_name": clean,
                }

        print(f"Smart Craft: {len(ah_lbin_map)} farkli AH esyasi ve {len(bazaar_dict)} Bazaar urunu ile karar agaci cozuluyor...")

        # 5. Her esya icin "Buy vs Craft" Karar Fonksiyonu (Memoized / Recursive)
        memo: Dict[str, Tuple[Optional[float], List[Dict[str, Any]], float]] = {}

        def is_raw_compactor(recipe: Recipe) -> bool:
            """160 ham esya -> 1 enchantli esya gibi compactor tariflerini tespit eder."""
            if len(recipe.ingredients) == 1:
                ing = recipe.ingredients[0]
                if ing.quantity >= 32 and not ing.item_id.startswith("ENCHANTED_"):
                    return True
            return False

        def resolve_cost(item_id: str, depth: int = 0) -> Tuple[Optional[float], List[Dict[str, Any]], float]:
            if item_id in memo:
                return memo[item_id]

            item_obj = items_dict.get(item_id)
            item_name = item_obj.name if item_obj else item_id.replace("_", " ").title()

            # Secenek 1: Bazaar'dan Buy Order ile satin alma maliyeti
            bazaar_buy_cost = None
            if item_id in bazaar_dict and float(bazaar_dict[item_id].sell_price) > 0:
                bazaar_buy_cost = float(bazaar_dict[item_id].sell_price)
            elif item_obj and item_obj.npc_sell_price:
                bazaar_buy_cost = float(item_obj.npc_sell_price)

            # Secenek 2: Auction House'dan LBIN ile satin alma maliyeti
            ah_buy_cost = None
            base_name_lower = item_name.lower()
            if base_name_lower in ah_lbin_map:
                ah_buy_cost = ah_lbin_map[base_name_lower]["price"]

            # Secenek 3: Craftlama Maliyeti
            craft_cost = None
            craft_substeps = []
            if item_id in recipe_dict and depth < 2:
                r = recipe_dict[item_id][0]
                # Eger bu esya tek bir ham maddeden olusan compactor esyasiysa (orn: 160 Flint -> Enchanted Flint)
                # ve Bazaar'da satiliyorsa, ara urun olarak sifirdan yuzbinlerce ham madde alip craftlamak yerine
                # dogrudan Bazaar'dan enchantli halini al.
                if depth >= 1 and item_id in bazaar_dict and is_raw_compactor(r):
                    pass
                else:
                    possible_cost = 0.0
                    can_craft = True
                    temp_steps = []

                    for ing in r.ingredients:
                        ing_cost, sub_s, sub_sav = resolve_cost(ing.item_id, depth + 1)
                        if ing_cost is None or ing_cost <= 0:
                            can_craft = False
                            break
                        possible_cost += ing_cost * ing.quantity
                        for s in sub_s:
                            temp_steps.append({
                                "action": s["action"],
                                "item_id": s["item_id"],
                                "item_name": s["item_name"],
                                "quantity": s["quantity"] * ing.quantity,
                                "unit_price": s["unit_price"],
                                "total_price": s["total_price"] * ing.quantity,
                                "note": s.get("note"),
                                "is_intermediate_craft": s.get("is_intermediate_craft", False),
                                "savings_total": s.get("savings_total", 0.0) * ing.quantity,
                            })

                    if can_craft and possible_cost > 0:
                        yield_qty = r.result_quantity or 1
                        craft_cost = possible_cost / yield_qty
                        if yield_qty != 1:
                            for s in temp_steps:
                                s["quantity"] = s["quantity"] / yield_qty
                                s["total_price"] = s["total_price"] / yield_qty
                                s["savings_total"] = s["savings_total"] / yield_qty
                        craft_substeps = temp_steps

            # En ucuz secenegi belirle
            market_cost = None
            market_type = None

            if bazaar_buy_cost is not None and ah_buy_cost is not None:
                if bazaar_buy_cost <= ah_buy_cost:
                    market_cost = bazaar_buy_cost
                    market_type = "BUY_BAZAAR"
                else:
                    market_cost = ah_buy_cost
                    market_type = "BUY_AH"
            elif bazaar_buy_cost is not None:
                market_cost = bazaar_buy_cost
                market_type = "BUY_BAZAAR"
            elif ah_buy_cost is not None:
                market_cost = ah_buy_cost
                market_type = "BUY_AH"

            best_cost = None
            savings = 0.0
            steps = []

            if craft_cost is not None and market_cost is not None and depth > 0:
                if market_cost <= craft_cost:
                    best_cost = market_cost
                    savings = craft_cost - market_cost
                    note = f"💡 Hazır satın almak, sıfırdan craftlamaktan {round(savings):,} coins daha ucuz!"
                    steps = [{
                        "action": market_type,
                        "item_id": item_id,
                        "item_name": item_name,
                        "quantity": 1,
                        "unit_price": market_cost,
                        "total_price": market_cost,
                        "note": note,
                        "is_intermediate_craft": False,
                        "savings_total": savings,
                    }]
                else:
                    best_cost = craft_cost
                    savings = market_cost - craft_cost
                    steps = craft_substeps + [{
                        "action": "CRAFT",
                        "item_id": item_id,
                        "item_name": item_name,
                        "quantity": 1,
                        "unit_price": craft_cost,
                        "total_price": craft_cost,
                        "note": None,
                        "is_intermediate_craft": True,
                        "savings_total": savings,
                    }]
            elif craft_cost is not None and depth > 0:
                best_cost = craft_cost
                steps = craft_substeps + [{
                    "action": "CRAFT",
                    "item_id": item_id,
                    "item_name": item_name,
                    "quantity": 1,
                    "unit_price": craft_cost,
                    "total_price": craft_cost,
                    "note": None,
                    "is_intermediate_craft": True,
                    "savings_total": 0.0,
                }]
            elif market_cost is not None:
                best_cost = market_cost
                steps = [{
                    "action": market_type,
                    "item_id": item_id,
                    "item_name": item_name,
                    "quantity": 1,
                    "unit_price": market_cost,
                    "total_price": market_cost,
                    "note": None,
                    "is_intermediate_craft": False,
                    "savings_total": 0.0,
                }]

            memo[item_id] = (best_cost, steps, savings)
            return memo[item_id]

        # 6. Tum tarifler icin en karli ciktiyi hesapla
        results: List[SmartCraftFlipItem] = []

        for result_item_id, recipes in recipe_dict.items():
            r = recipes[0]
            item_obj = items_dict.get(result_item_id)
            item_name = item_obj.name if item_obj else result_item_id.replace("_", " ").title()

            total_cost = 0.0
            raw_steps = []
            total_savings = 0.0
            possible = True

            for ing in r.ingredients:
                ing_cost, sub_s, sub_sav = resolve_cost(ing.item_id, depth=1)
                if ing_cost is None or ing_cost <= 0:
                    possible = False
                    break
                total_cost += ing_cost * ing.quantity
                total_savings += sub_sav * ing.quantity
                for s in sub_s:
                    raw_steps.append({
                        "action": s["action"],
                        "item_id": s["item_id"],
                        "item_name": s["item_name"],
                        "quantity": s["quantity"] * ing.quantity,
                        "unit_price": s["unit_price"],
                        "total_price": s["total_price"] * ing.quantity,
                        "note": s.get("note"),
                        "is_intermediate_craft": s.get("is_intermediate_craft", False),
                        "savings_total": s.get("savings_total", 0.0) * ing.quantity,
                    })

            if not possible or total_cost <= 0:
                continue

            if max_budget is not None and total_cost > max_budget:
                continue

            sell_options = []

            # 1. Option: AH'ye satmak
            base_lower = item_name.lower()
            if base_lower in ah_lbin_map:
                ah_info = ah_lbin_map[base_lower]
                ah_sell_price = ah_info["price"]
                ah_net_revenue = ah_sell_price * 0.98
                ah_profit = ah_net_revenue - total_cost
                if ah_profit >= min_profit:
                    sell_options.append({
                        "market": "AUCTION_HOUSE",
                        "price": ah_sell_price,
                        "net_revenue": ah_net_revenue,
                        "profit": ah_profit,
                        "tier": ah_info.get("tier"),
                        "category": ah_info.get("category"),
                        "action_sell": f"Auction House'a Lowest BIN olarak {round(ah_sell_price * 0.99):,} coins fiyata koy",
                    })

            # 2. Option: Bazaar'a satmak
            if result_item_id in bazaar_dict:
                bz_snap = bazaar_dict[result_item_id]
                bz_sell_price = float(bz_snap.buy_price)
                if bz_sell_price > 0:
                    bz_net_revenue = bz_sell_price * (1 - settings.BAZAAR_TAX_RATE)
                    bz_profit = bz_net_revenue - total_cost
                    if bz_profit >= min_profit:
                        sell_options.append({
                            "market": "BAZAAR",
                            "price": bz_sell_price,
                            "net_revenue": bz_net_revenue,
                            "profit": bz_profit,
                            "tier": item_obj.tier if item_obj else None,
                            "category": item_obj.category if item_obj else None,
                            "action_sell": f"Bazaar'a Sell Offer olarak {round(bz_sell_price):,} coins fiyata koy",
                        })

            if not sell_options:
                continue

            for opt in sell_options:
                if market_filter == "ah" and opt["market"] != "AUCTION_HOUSE":
                    continue
                if market_filter == "bazaar" and opt["market"] != "BAZAAR":
                    continue

                profit = opt["profit"]
                margin_pct = (profit / total_cost) * 100.0
                if margin_pct < min_margin:
                    continue

                formatted_steps: List[SmartCraftStep] = []
                step_no = 1

                # 1. Alis adimlari (Bazaar / AH Buy)
                buy_groups = defaultdict(lambda: {"qty": 0.0, "total": 0.0, "action": "", "name": "", "notes": []})
                for s in raw_steps:
                    if s["action"].startswith("BUY"):
                        k = (s["item_id"], s["action"])
                        buy_groups[k]["qty"] += s["quantity"]
                        buy_groups[k]["total"] += s["total_price"]
                        buy_groups[k]["action"] = s["action"]
                        buy_groups[k]["name"] = s["item_name"]
                        if s.get("note"):
                            buy_groups[k]["notes"].append(s["note"])

                for k, bg in buy_groups.items():
                    qty = int(round(bg["qty"]))
                    unit_p = bg["total"] / max(1, qty)
                    formatted_steps.append(
                        SmartCraftStep(
                            step_number=step_no,
                            action_type=bg["action"],
                            item_name=bg["name"],
                            item_id=k[0],
                            quantity=qty,
                            unit_price=round(unit_p, 1),
                            total_price=round(bg["total"], 1),
                            note=" | ".join(set(bg["notes"])) if bg["notes"] else None,
                        )
                    )
                    step_no += 1

                # 2. Ara Craft Adimlari (Orn: 102x Tarantula Silk uret)
                intermediate_crafts = defaultdict(lambda: {"qty": 0.0, "total": 0.0, "name": "", "savings": 0.0})
                for s in raw_steps:
                    if s["action"] == "CRAFT" and s.get("is_intermediate_craft"):
                        k = s["item_id"]
                        intermediate_crafts[k]["qty"] += s["quantity"]
                        intermediate_crafts[k]["total"] += s["total_price"]
                        intermediate_crafts[k]["name"] = s["item_name"]
                        intermediate_crafts[k]["savings"] += s.get("savings_total", 0.0)

                for item_id, ic in intermediate_crafts.items():
                    qty = int(round(ic["qty"]))
                    unit_p = ic["total"] / max(1, qty)
                    note_txt = f"Crafting Table'da {qty}x {ic['name']} uret"
                    if ic["savings"] > 0:
                        note_txt += f" (💡 Sifirdan craftlamak, hazir almaktan {round(ic['savings']):,} coins daha ucuz!)"
                    formatted_steps.append(
                        SmartCraftStep(
                            step_number=step_no,
                            action_type="CRAFT",
                            item_name=ic["name"],
                            item_id=item_id,
                            quantity=qty,
                            unit_price=round(unit_p, 1),
                            total_price=round(ic["total"], 1),
                            note=note_txt,
                        )
                    )
                    step_no += 1

                # 3. Nihai Hedef Craft Adimi (Orn: 1x Flycatcher uret)
                formatted_steps.append(
                    SmartCraftStep(
                        step_number=step_no,
                        action_type="CRAFT",
                        item_name=item_name,
                        item_id=result_item_id,
                        quantity=r.result_quantity,
                        unit_price=round(total_cost, 1),
                        total_price=round(total_cost, 1),
                        note=f"Crafting Table'da {r.result_quantity}x {item_name} uret",
                    )
                )
                step_no += 1

                # 4. Satis Adimi (AH veya Bazaar)
                formatted_steps.append(
                    SmartCraftStep(
                        step_number=step_no,
                        action_type="SELL_AH" if opt["market"] == "AUCTION_HOUSE" else "SELL_BAZAAR",
                        item_name=item_name,
                        item_id=result_item_id,
                        quantity=r.result_quantity,
                        unit_price=round(opt["price"], 1),
                        total_price=round(opt["price"], 1),
                        note=opt["action_sell"],
                    )
                )

                hourly_vol = 5
                if opt["market"] == "BAZAAR" and result_item_id in bazaar_dict:
                    hourly_vol = int(bazaar_dict[result_item_id].sell_moving_week / 168)

                pph = profit * min(60.0, max(1.0, hourly_vol * 0.10))

                results.append(
                    SmartCraftFlipItem(
                        result_item_id=result_item_id,
                        result_name=item_name,
                        tier=opt["tier"],
                        category=opt["category"],
                        target_market=opt["market"],
                        optimal_cost=round(total_cost, 1),
                        sell_price=round(opt["price"], 1),
                        net_revenue=round(opt["net_revenue"], 1),
                        net_profit=round(profit, 1),
                        margin_percent=round(margin_pct, 1),
                        savings=round(total_savings, 1),
                        hourly_volume=hourly_vol,
                        profit_per_hour=round(pph, 1),
                        steps=formatted_steps,
                    )
                )

        results.sort(key=lambda x: x.net_profit, reverse=True)
        return results[:limit]


smart_craft_engine = SmartCraftEngine()
