import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine, Base
import app.models
from app.api.v1.router import api_router
from app.services.bazaar_service import sync_bazaar_to_db
from app.services.auction_recorder import sync_ended_auctions_to_db

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def bazaar_background_updater():
    """Arka planda her 90 saniyede bir Bazaar verilerini otomatik gunceller."""
    while True:
        try:
            await asyncio.sleep(90)
            async with AsyncSessionLocal() as session:
                await sync_bazaar_to_db(session)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Bazaar arka plan guncelleme hatasi: {e}")


async def ah_sales_recorder_loop():
    """Arka planda her 60 saniyede bir Hypixel auctions_ended endpoint'ini dinler ve satis gecmisini PostgreSQL'e kaydeder."""
    while True:
        try:
            await asyncio.sleep(60)
            async with AsyncSessionLocal() as session:
                saved = await sync_ended_auctions_to_db(session)
                if saved > 0:
                    print(f"[DB] {saved} yeni Auction House satisi veritabanina kaydedildi.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"AH satis kaydetme hatasi: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama baslatildiginda calisacak gorevler."""
    print("[INFO] Skyblock Buffet Backend Baslatiliyor...")
    # Tablolari kontrol et ve varsa eksik tablolari olustur
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    t1 = asyncio.create_task(bazaar_background_updater())
    t2 = asyncio.create_task(ah_sales_recorder_loop())
    yield
    t1.cancel()
    t2.cancel()
    print("[INFO] Skyblock Buffet Backend Kapatildi.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Skyblock Buffet API calisiyor!", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
