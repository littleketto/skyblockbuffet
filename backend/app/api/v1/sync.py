from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.services.item_service import sync_items_to_db
from app.services.bazaar_service import sync_bazaar_to_db
from app.services.recipe_service import sync_recipes_to_db

router = APIRouter(prefix="/sync", tags=["Veri Senkronizasyonu"])


async def _background_sync_bazaar():
    async with AsyncSessionLocal() as session:
        await sync_bazaar_to_db(session)


@router.post("/bazaar")
async def trigger_bazaar_sync(background_tasks: BackgroundTasks):
    """Bazaar anlik verilerini arka planda gunceller."""
    background_tasks.add_task(_background_sync_bazaar)
    return {"message": "Bazaar senkronizasyonu arka planda baslatildi."}


@router.post("/items")
async def trigger_items_sync(db: AsyncSession = Depends(get_db)):
    """Hypixel 5.600+ esya listesini gunceller."""
    count = await sync_items_to_db(db)
    return {"message": f"{count} esya basariyla senkronize edildi."}


@router.post("/recipes")
async def trigger_recipes_sync(db: AsyncSession = Depends(get_db)):
    """NotEnoughUpdates deposundaki 2.000+ tarifi gunceller."""
    recipes, ingredients = await sync_recipes_to_db(db)
    return {"message": f"{recipes} tarif ve {ingredients} hammadde kaydedildi."}
