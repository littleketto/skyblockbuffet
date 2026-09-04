from fastapi import APIRouter
from app.api.v1.bazaar import router as bazaar_router
from app.api.v1.craft import router as craft_router
from app.api.v1.auction import router as auction_router
from app.api.v1.sync import router as sync_router

api_router = APIRouter()
api_router.include_router(bazaar_router)
api_router.include_router(craft_router)
api_router.include_router(auction_router)
api_router.include_router(sync_router)
