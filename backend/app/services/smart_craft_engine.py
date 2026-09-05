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
from app.services.auction_service import auction_service, clean_minecraft_text, extract_base_item_name, extract_item_info_from_bytes
from app.services.coflnet_service import coflnet_service


def format_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "0 sn"
    if seconds < 60:
        return f"{seconds} sn"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} dk"
    hours = seconds / 3600.0
    if hours.is_integer():
        return f"{int(hours)} sa"
    return f"{hours:.1f} sa"


class SmartCraftEngine:
    """
    Akilli Cok Asamali Craft Flipping & AH Entegrasyon Motoru
    - Bazaar'dan hammadde alip AH'de satma fırsatlarını bulur.
    - Ara esyalar icin (Buy vs Craft) karsilastirmasi yaparak en ucuz yolu secer.
    - Adim adim yol haritasi (Action Plan) uretir.
    - Crafting Table ve Dwarven Forge dökümünü bağımsız analiz eder.
    """

    async def calculate_smart_flips(
        self,
        db: AsyncSession,
        market_filter: str = "all", # "all", "ah", "bazaar"
        buy_mode: str = "buy_order", # "buy_order" veya "insta_buy"
        bazaar_sell_mode: str = "sell_offer", # "sell_offer" veya "insta_sell"
        recipe_type: str = "crafting", # "crafting", "forge" veya "all"
        min_profit: float = 0.0,
        min_margin: float = 0.0,
        max_budget: Optional[float] = None,
        limit: int = 3000,
    ) -> List[SmartCraftFlipItem]:
        print(f"Smart Craft Engine ({recipe_type}): Piyasa verileri ve aktif ilanlar toplaniyor...")

        # 1. Bazaar verilerini yukle
        bazaar_res = await db.execute(select(BazaarSnapshot))
        bazaar_dict: Dict[str, BazaarSnapshot] = {b.item_id: b for b in bazaar_res.scalars().all()}

        # 2. Tum Item bilgilerini yukle
        items_res = await db.execute(select(Item))
        items_list = items_res.scalars().all()
        items_dict: Dict[str, Item] = {it.id: it for it in items_list}

        # 3. Tum tarifleri yukle ve turune gore ayir
        recipes_res = await db.execute(
            select(Recipe).where(Recipe.is_active == True).options(selectinload(Recipe.ingredients))
        )
        all_recipes = recipes_res.scalars().all()

        craft_recipes_dict: Dict[str, List[Recipe]] = defaultdict(list)
        forge_recipes_dict: Dict[str, List[Recipe]] = defaultdict(list)
        all_recipes_dict: Dict[str, List[Recipe]] = defaultdict(list)

        for r in all_recipes:
            all_recipes_dict[r.result_item_id].append(r)
            if r.recipe_type == "forge":
                forge_recipes_dict[r.result_item_id].append(r)
            else:
                craft_recipes_dict[r.result_item_id].append(r)

        if recipe_type == "forge":
            target_recipe_dict = forge_recipes_dict
            intermediate_recipe_dict = all_recipes_dict
        elif recipe_type == "crafting":
            target_recipe_dict = craft_recipes_dict
            intermediate_recipe_dict = craft_recipes_dict
        else:
            target_recipe_dict = all_recipes_dict
            intermediate_recipe_dict = all_recipes_dict

        # 4. Auction House aktif BIN ilanlarini topla: { clean_name_lower: (lbin, auction_uuid, tier, category, listings_count, median_price) }
        bin_auctions = await auction_service.fetch_all_bin_auctions(max_concurrent=15)
        ah_lbin_map: Dict[str, Dict[str, Any]] = {}
        ah_auctions_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for a in bin_auctions:
            raw_name = a.get("item_name", "")
            clean = clean_minecraft_text(raw_name)
            base_name = extract_base_item_name(clean).lower()
            price = float(a.get("starting_bid", 0))
            if price <= 1000:
                continue
            ah_auctions_by_name[base_name].append(a)

        for base_name, aucs in ah_auctions_by_name.items():
            aucs.sort(key=lambda x: float(x.get("starting_bid", 0)))
            lbin_auc = aucs[0]
            price = float(lbin_auc.get("starting_bid", 0))
            prices = [float(x.get("starting_bid", 0)) for x in aucs]
            median_p = sum(prices[:min(5, len(prices))]) / min(5, len(prices))
            second_p = prices[1] if len(prices) > 1 else price
            ah_lbin_map[base_name] = {
                "price": price,
                "uuid": lbin_auc.get("uuid", ""),
                "tier": lbin_auc.get("tier"),
                "category": lbin_auc.get("category"),
                "full_name": clean_minecraft_text(lbin_auc.get("item_name", "")),
                "listings_count": len(aucs),
                "second_price": second_p,
                "median_price": median_p,
            }

        print(f"Smart Craft: {len(ah_lbin_map)} farkli AH esyasi ve {len(bazaar_dict)} Bazaar urunu ile karar agaci cozuluyor...")


        # 5. Her esya icin "Buy vs Craft" Karar Fonksiyonu (Memoized / Recursive)
        memo: Dict[str, Tuple[Optional[float], List[Dict[str, Any]], float]] = {}
        visiting: set = set()

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
            if item_id in visiting:
                return (None, [], 0.0)

            visiting.add(item_id)

            item_obj = items_dict.get(item_id)
            item_name = item_obj.name if item_obj else item_id.replace("_", " ").title()

            # Secenek 1: Bazaar'dan satin alma maliyeti (Buy Order veya Insta-Buy)
            bazaar_buy_cost = None
            bazaar_action_type = "INSTA_BUY_BAZAAR" if buy_mode == "insta_buy" else "BUY_BAZAAR"
            if item_id in bazaar_dict:
                bz_s = bazaar_dict[item_id]
                if buy_mode == "insta_buy":
                    # Insta-Buy: Aninda almak icin Sell Offer fiyatindan (buy_price) aliriz
                    if float(bz_s.buy_price) > 0:
                        bazaar_buy_cost = float(bz_s.buy_price)
                    elif float(bz_s.sell_price) > 0:
                        bazaar_buy_cost = float(bz_s.sell_price)
                else:
                    # Buy Order: Siparis acarak almak icin Buy Order fiyatindan (sell_price) aliriz
                    if float(bz_s.sell_price) > 0:
                        bazaar_buy_cost = float(bz_s.sell_price)
                    elif float(bz_s.buy_price) > 0:
                        bazaar_buy_cost = float(bz_s.buy_price)

            # Secenek 2: Auction House'dan LBIN ile satin alma maliyeti
            ah_buy_cost = None
            base_name_lower = item_name.lower()
            if base_name_lower in ah_lbin_map:
                ah_buy_cost = ah_lbin_map[base_name_lower]["price"]

            # Secenek 3: Craftlama / Döküm Maliyeti
            craft_cost = None
            craft_substeps = []
            if item_id in intermediate_recipe_dict and depth < 4:
                r = intermediate_recipe_dict[item_id][0]
                is_sub_forge = (r.recipe_type == "forge")
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
                    market_type = bazaar_action_type
                else:
                    market_cost = ah_buy_cost
                    market_type = "BUY_AH"
            elif bazaar_buy_cost is not None:
                market_cost = bazaar_buy_cost
                market_type = bazaar_action_type
            elif ah_buy_cost is not None:
                market_cost = ah_buy_cost
                market_type = "BUY_AH"

            best_cost = None
            savings = 0.0
            steps = []

            inter_action = "FORGE" if (item_id in intermediate_recipe_dict and intermediate_recipe_dict[item_id][0].recipe_type == "forge") else "CRAFT"

            if craft_cost is not None and market_cost is not None and depth > 0:
                if market_cost <= craft_cost:
                    best_cost = market_cost
                    savings = craft_cost - market_cost
                    note = f"💡 Hazır satın almak, sıfırdan üretmekten {round(savings):,} coins daha ucuz!"
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
                        "action": inter_action,
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
                    "action": inter_action,
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
            visiting.remove(item_id)
            return memo[item_id]

        # 6. Tum tarifler icin en karli cikti adaylarini topla
        candidates: List[Dict[str, Any]] = []

        for result_item_id, recipes in target_recipe_dict.items():
            r = recipes[0]
            item_obj = items_dict.get(result_item_id)
            item_name = item_obj.name if item_obj else result_item_id.replace("_", " ").title()
            is_item_forge = (r.recipe_type == "forge")
            item_dur_sec = getattr(r, "duration_seconds", 0) or 0
            item_dur_disp = format_duration(item_dur_sec)

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

            # 2. Option: Bazaar'a satmak (Sell Offer veya Insta-Sell)
            if result_item_id in bazaar_dict:
                bz_snap = bazaar_dict[result_item_id]
                if bazaar_sell_mode == "insta_sell":
                    # Insta-Sell: Aninda bozdurmak icin en yuksek Buy Order fiyatindan (sell_price) satariz
                    bz_sell_price = float(bz_snap.sell_price)
                    action_sell_txt = f"Bazaar'a Anında Sat (Insta-Sell) ile {round(bz_sell_price):,} coins fiyata sat"
                    bazaar_sell_action = "INSTA_SELL_BAZAAR"
                else:
                    # Sell Offer: Siparis acarak en yuksek fiyattan (buy_price) satariz
                    bz_sell_price = float(bz_snap.buy_price)
                    action_sell_txt = f"Bazaar'a Sell Offer olarak {round(bz_sell_price):,} coins fiyata koy"
                    bazaar_sell_action = "SELL_BAZAAR"

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
                            "action_sell": action_sell_txt,
                            "sell_action_type": bazaar_sell_action,
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

                # 2. Ara Uretim Adimlari (Crafting Table veya Dwarven Forge)
                intermediate_crafts = defaultdict(lambda: {"qty": 0.0, "total": 0.0, "name": "", "savings": 0.0, "action": "CRAFT"})
                for s in raw_steps:
                    if s["action"] in ("CRAFT", "FORGE") and s.get("is_intermediate_craft"):
                        k = s["item_id"]
                        intermediate_crafts[k]["qty"] += s["quantity"]
                        intermediate_crafts[k]["total"] += s["total_price"]
                        intermediate_crafts[k]["name"] = s["item_name"]
                        intermediate_crafts[k]["savings"] += s.get("savings_total", 0.0)
                        intermediate_crafts[k]["action"] = s["action"]

                for item_id, ic in intermediate_crafts.items():
                    qty = int(round(ic["qty"]))
                    unit_p = ic["total"] / max(1, qty)
                    inter_prefix = "Dwarven Forge'da" if ic["action"] == "FORGE" else "Crafting Table'da"
                    note_txt = f"{inter_prefix} {qty}x {ic['name']} uret"
                    if ic["savings"] > 0:
                        note_txt += f" (💡 Sifirdan üretmek, hazir almaktan {round(ic['savings']):,} coins daha ucuz!)"
                    formatted_steps.append(
                        SmartCraftStep(
                            step_number=step_no,
                            action_type=ic["action"],
                            item_name=ic["name"],
                            item_id=item_id,
                            quantity=qty,
                            unit_price=round(unit_p, 1),
                            total_price=round(ic["total"], 1),
                            note=note_txt,
                        )
                    )
                    step_no += 1

                # 3. Nihai Hedef Uretim Adimi (Crafting Table veya Dwarven Forge)
                final_action = "FORGE" if is_item_forge else "CRAFT"
                final_note = f"Dwarven Forge'da {item_dur_disp} döküm yap ({r.result_quantity}x {item_name})" if is_item_forge else f"Crafting Table'da {r.result_quantity}x {item_name} uret"
                formatted_steps.append(
                    SmartCraftStep(
                        step_number=step_no,
                        action_type=final_action,
                        item_name=item_name,
                        item_id=result_item_id,
                        quantity=r.result_quantity,
                        unit_price=round(total_cost, 1),
                        total_price=round(total_cost, 1),
                        note=final_note,
                    )
                )
                step_no += 1

                # 4. Satis Adimi (AH veya Bazaar)
                sell_step_action = "SELL_AH" if opt["market"] == "AUCTION_HOUSE" else opt.get("sell_action_type", "SELL_BAZAAR")
                formatted_steps.append(
                    SmartCraftStep(
                        step_number=step_no,
                        action_type=sell_step_action,
                        item_name=item_name,
                        item_id=result_item_id,
                        quantity=r.result_quantity,
                        unit_price=round(opt["price"], 1),
                        total_price=round(opt["price"], 1),
                        note=opt["action_sell"],
                    )
                )

                candidates.append({
                    "result_item_id": result_item_id,
                    "item_name": item_name,
                    "tier": opt["tier"],
                    "category": opt["category"],
                    "recipe_type": r.recipe_type,
                    "duration_seconds": item_dur_sec,
                    "duration_display": item_dur_disp,
                    "opt": opt,
                    "total_cost": total_cost,
                    "profit": profit,
                    "margin_pct": margin_pct,
                    "total_savings": total_savings,
                    "formatted_steps": formatted_steps,
                })

        # AH hedeflerinin gercek satis gecmisini Coflnet'ten paralel cek
        ah_candidates = [c for c in candidates if c["opt"]["market"] == "AUCTION_HOUSE"]
        ah_candidates.sort(key=lambda c: c["profit"], reverse=True)
        top_ah_ids = list(dict.fromkeys(c["result_item_id"] for c in ah_candidates[:40]))

        histories_map: Dict[str, Any] = {}
        if top_ah_ids:
            try:
                histories_map = await coflnet_service.get_multiple_items_history_24h(top_ah_ids, max_concurrent=10)
            except Exception as e:
                print(f"Coflnet batch cekme hatasi: {e}")

        results: List[SmartCraftFlipItem] = []
        for c in candidates:
            result_item_id = c["result_item_id"]
            item_name = c["item_name"]
            opt = c["opt"]
            total_cost = c["total_cost"]
            profit = c["profit"]
            margin_pct = c["margin_pct"]
            total_savings = c["total_savings"]
            formatted_steps = c["formatted_steps"]

            if opt["market"] == "BAZAAR" and result_item_id in bazaar_dict:
                bz_snap = bazaar_dict[result_item_id]
                if bazaar_sell_mode == "insta_sell":
                    # Insta-sell durumunda buy_moving_week (bekleyen buy order'larin haftalik alim hacmi)
                    # ve sell_price (anlik satis fiyati) kullanilir
                    raw_vol_7d = int(bz_snap.buy_moving_week) if bz_snap.buy_moving_week else int(bz_snap.sell_moving_week)
                    vol_7d = max(0, raw_vol_7d)
                    vol_24h = int(round(vol_7d / 7.0))
                    avg_price_24h = round(float(bz_snap.sell_price), 1)
                    avg_price_7d = round(float(bz_snap.sell_price), 1)
                else:
                    vol_7d = int(bz_snap.sell_moving_week)
                    vol_24h = int(round(vol_7d / 7.0))
                    avg_price_24h = round(float(bz_snap.buy_price), 1)
                    avg_price_7d = round(float(bz_snap.buy_price), 1)

                if vol_7d <= 0 or vol_24h <= 0:
                    liquidity_status = "RISKLI"
                    risk_warning = "Bazaar'da talep yok (Hacim: 0). Satın alan oyuncu yok!"
                    hourly_vol = 0
                    pph = 0.0
                else:
                    hourly_vol = max(1, round(vol_24h / 24.0))
                    if vol_24h >= 20:
                        liquidity_status = "YUKSEK"
                        risk_warning = None
                    elif vol_24h >= 5:
                        liquidity_status = "ORTA"
                        risk_warning = None
                    else:
                        liquidity_status = "RISKLI"
                        risk_warning = f"Son 24 saatte sadece {vol_24h} adet satıldı."
                    hourly_cap = min(15.0, max(0.1, hourly_vol * 0.12))
                    pph = round(profit * hourly_cap, 0)
            else:
                # AUCTION_HOUSE
                base_lower = item_name.lower()
                ah_info = ah_lbin_map.get(base_lower, {})
                listings_count = ah_info.get("listings_count", 1)
                median_p = ah_info.get("median_price", opt["price"])
                history = histories_map.get(result_item_id)

                # Absurt / Sahte Ilan Kontrolu (Maliyeti cok dusuk ama ilan fiyati asiri sisirilmis sahte ilanlar)
                is_absurd_markup = (listings_count <= 1 and (opt["price"] / max(1.0, total_cost)) > 10.0 and opt["price"] > 10_000_000)

                if history and history.get("daily_volume", 0) > 0:
                    vol_24h = history["daily_volume"]
                    vol_7d = vol_24h * 7
                    avg_price_24h = round(history["avg_price"], 0)
                    avg_price_7d = round(history["avg_price"], 0)

                    # Eger aktif ilan, 24 saatlik gercek satis ortalamasindan 3 kat fazlaysa ve tek ilansa sahtedir
                    if opt["price"] > 3.0 * avg_price_24h and listings_count <= 2:
                        liquidity_status = "RISKLI"
                        risk_warning = f"⚠️ İlan fiyatı ({round(opt['price']):,}) 24s ortalamadan ({round(avg_price_24h):,}) çok yüksek!"
                        hourly_vol = 0
                        pph = 0.0
                    else:
                        if vol_24h >= 10:
                            liquidity_status = "YUKSEK"
                            risk_warning = None
                        elif vol_24h >= 3:
                            liquidity_status = "ORTA"
                            risk_warning = None
                        else:
                            liquidity_status = "RISKLI"
                            risk_warning = f"Düşük pazar hacmi (~{vol_24h} adet/gün)."

                        hourly_vol = max(1, round(vol_24h / 24.0))
                        hourly_cap = min(12.0, max(0.1, hourly_vol * 0.15))
                        pph = round(profit * hourly_cap, 0)

                elif is_absurd_markup:
                    # Sadece gercekten sahte/manipule ilanlar 0 hacimli yapilir
                    vol_24h = 0
                    vol_7d = 0
                    avg_price_24h = round(opt["price"], 0)
                    avg_price_7d = round(opt["price"], 0)
                    liquidity_status = "RISKLI"
                    risk_warning = "⚠️ Absürt / Sahte Satış Fiyatı! Pazarda sadece 1 ilan var."
                    hourly_vol = 0
                    pph = 0.0

                else:
                    # Mesru craft esyasi (Gigantic Fishing Net vb.):
                    # Yuksek degerli esyalar pazarda dogal olarak az sayida ilana sahiptir, 0 hacimli degildir.
                    if total_cost >= 10_000_000 or opt["price"] >= 15_000_000:
                        if listings_count >= 3:
                            vol_24h = round(listings_count * 2.0)
                        elif listings_count == 2:
                            vol_24h = 5
                        else:
                            vol_24h = 3
                        vol_7d = vol_24h * 7
                        avg_price_24h = round(median_p, 0)
                        avg_price_7d = round(median_p, 0)
                        liquidity_status = "ORTA"
                        risk_warning = None if listings_count >= 2 else "Pazarda 1 aktif ilan var (~3 satış/gün)."
                        hourly_vol = max(1, round(vol_24h / 24.0))
                        hourly_cap = min(12.0, max(0.1, hourly_vol * 0.15))
                        pph = round(profit * hourly_cap, 0)
                    else:
                        if listings_count >= 3:
                            vol_24h = round(listings_count * 1.5)
                        elif listings_count == 2:
                            vol_24h = 3
                        else:
                            vol_24h = 2
                        vol_7d = vol_24h * 7
                        avg_price_24h = round(median_p, 0)
                        avg_price_7d = round(median_p, 0)
                        liquidity_status = "ORTA" if vol_24h >= 4 else "RISKLI"
                        risk_warning = None if listings_count >= 2 else "Pazarda 1 aktif ilan var."
                        hourly_vol = max(1, round(vol_24h / 24.0))
                        hourly_cap = min(12.0, max(0.1, hourly_vol * 0.15))
                        pph = round(profit * hourly_cap, 0)

            cand_recipe_type = c.get("recipe_type", "crafting")
            cand_dur_sec = c.get("duration_seconds", 0)
            cand_dur_disp = c.get("duration_display", "0 sn")
            is_cand_forge = (cand_recipe_type == "forge")

            # Forge esyalari icin Saatlik Slot Kari (PPH) hesabi:
            # Net Kar / Döküm Saati (orn: 6 saat ise kar/6)
            if is_cand_forge:
                dur_hours = max(cand_dur_sec / 3600.0, 30.0 / 3600.0)
                if dur_hours < 1.0:
                    max_crafts_per_hour = 3600.0 / max(30, cand_dur_sec)
                    vol_cap = max(0.1, min(max_crafts_per_hour, max(1, hourly_vol) * 1.0))
                    pph = round(profit * vol_cap, 1)
                else:
                    pph = round(profit / dur_hours, 1)

                if vol_7d <= 0 or vol_24h <= 0:
                    liquidity_status = "RISKLI"
                    risk_warning = "Pazarda talep yok (Hacim: 0). Satın alan oyuncu yok!"
                    pph = 0.0

            results.append(
                SmartCraftFlipItem(
                    result_item_id=result_item_id,
                    result_name=item_name,
                    tier=opt["tier"],
                    category=opt["category"],
                    recipe_type=cand_recipe_type,
                    duration_seconds=cand_dur_sec,
                    duration_display=cand_dur_disp,
                    target_market=opt["market"],
                    buy_mode=buy_mode,
                    bazaar_sell_mode=bazaar_sell_mode,
                    optimal_cost=round(total_cost, 1),
                    sell_price=round(opt["price"], 1),
                    net_revenue=round(opt["net_revenue"], 1),
                    net_profit=round(profit, 1),
                    margin_percent=round(margin_pct, 1),
                    savings=round(total_savings, 1),
                    hourly_volume=hourly_vol,
                    profit_per_hour=round(pph, 1),
                    avg_price_24h=avg_price_24h,
                    volume_24h=vol_24h,
                    avg_price_7d=avg_price_7d,
                    volume_7d=vol_7d,
                    liquidity_status=liquidity_status,
                    risk_warning=risk_warning,
                    steps=formatted_steps,
                )
            )

        # Siralama: Yuksek saatlik kar ve likiditeye sahip gercek firsatlar en basa,
        # 0 hacimli sahte / absurt ilanlar en sona
        results.sort(key=lambda x: (x.profit_per_hour, x.net_profit), reverse=True)
        return results[:limit]



smart_craft_engine = SmartCraftEngine()
