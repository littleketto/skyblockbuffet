import json
import urllib.request
import tarfile
from collections import defaultdict
from typing import List, Dict, Any, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.item import Item
from app.models.recipe import Recipe, RecipeIngredient

NEU_TARBALL_URL = "https://codeload.github.com/NotEnoughUpdates/NotEnoughUpdates-REPO/tar.gz/refs/heads/master"


def fetch_recipes_from_archive() -> List[Dict[str, Any]]:
    """
    NotEnoughUpdates resmi deposundan tum Skyblock tariflerini
    bellekte stream ederek parse eder.
    """
    print("NotEnoughUpdates deposundan tarif arsivi indiriliyor...")
    req = urllib.request.Request(NEU_TARBALL_URL, headers={"User-Agent": "Mozilla/5.0"})
    recipes = []

    with urllib.request.urlopen(req, timeout=45) as resp:
        with tarfile.open(fileobj=resp, mode="r|gz") as tar:
            for member in tar:
                if member.name.endswith(".json") and "/items/" in member.name:
                    f = tar.extractfile(member)
                    if not f:
                        continue
                    try:
                        data = json.load(f)
                        rec = data.get("recipe")
                        if isinstance(rec, dict):
                            item_id = data.get("internalname")
                            count = rec.get("count", 1)
                            if not isinstance(count, int) or count < 1:
                                count = 1

                            ingredients = defaultdict(int)
                            for slot, val in rec.items():
                                if slot == "count" or not val or not isinstance(val, str):
                                    continue
                                parts = val.split(":")
                                ing_id = parts[0].strip()
                                qty = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                                if ing_id:
                                    ingredients[ing_id] += qty

                            if ingredients and item_id:
                                recipes.append({
                                    "result_item_id": item_id,
                                    "result_quantity": count,
                                    "ingredients": dict(ingredients),
                                })
                    except Exception:
                        pass
    return recipes


async def sync_recipes_to_db(db: AsyncSession) -> Tuple[int, int]:
    """
    Tarifleri veritabanina aktarir:
    1. Eksik itemleri tespit eder ve foreign-key hatasi olmamasi icin otomatik ekler.
    2. 'recipes' ve 'recipe_ingredients' tablolarina kaydeder.
    """
    recipes_data = fetch_recipes_from_archive()
    if not recipes_data:
        print("Hic tarif bulunamadi!")
        return 0, 0

    print(f"Toplam {len(recipes_data)} tarif cikarildi. Veritabani foreign-key kontrolleri yapiliyor...")

    # 1. Tum tariflerde gecen item ID'lerini topla
    all_needed_item_ids = set()
    for r in recipes_data:
        all_needed_item_ids.add(r["result_item_id"])
        for ing_id in r["ingredients"].keys():
            all_needed_item_ids.add(ing_id)

    # 2. Veritabaninda halihazirda var olan itemleri cek
    existing_items_res = await db.execute(select(Item.id).where(Item.id.in_(all_needed_item_ids)))
    existing_item_ids = set(existing_items_res.scalars().all())

    # 3. Eksik olan itemleri placeholder olarak ekle (Vanilla esyalar vs.)
    missing_ids = all_needed_item_ids - existing_item_ids
    if missing_ids:
        print(f"{len(missing_ids)} adet tarif esyasi/hammaddesi 'items' tablosuna ekleniyor...")
        new_items = [
            {
                "id": mid,
                "name": mid.replace("_", " ").title(),
                "tier": "COMMON",
                "category": "MISC",
                "is_bazaar_item": False,
            }
            for mid in missing_ids
        ]
        # Chunking ile ekle
        for i in range(0, len(new_items), 500):
            stmt = insert(Item).values(new_items[i : i + 500]).on_conflict_do_nothing()
            await db.execute(stmt)
        await db.commit()

    # 4. Eski tarifleri temizle ve yenilerini kaydet
    print("Mevcut tarifler guncelleniyor...")
    await db.execute(delete(RecipeIngredient))
    await db.execute(delete(Recipe))
    await db.commit()

    total_recipes = 0
    total_ingredients = 0

    for r_data in recipes_data:
        recipe = Recipe(
            result_item_id=r_data["result_item_id"],
            result_quantity=r_data["result_quantity"],
            recipe_type="crafting",
            is_active=True,
        )
        db.add(recipe)
        await db.flush() # recipe.id olusmasi icin flush

        total_recipes += 1

        for ing_id, qty in r_data["ingredients"].items():
            db.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    item_id=ing_id,
                    quantity=qty,
                )
            )
            total_ingredients += 1

        if total_recipes % 400 == 0:
            await db.commit()

    await db.commit()
    print(f"Basarili! {total_recipes} tarif ve {total_ingredients} hammadde bileseni kaydedildi.")
    return total_recipes, total_ingredients
