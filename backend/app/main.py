import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.api.v1.router import api_router
from app.services.bazaar_service import sync_bazaar_to_db

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama baslatildiginda ve kapatildiginda calisacak gorevler."""
    print("[INFO] Skyblock Buffet Backend Baslatiliyor...")
    updater_task = asyncio.create_task(bazaar_background_updater())
    yield
    updater_task.cancel()
    print("[INFO] Skyblock Buffet Backend Kapatildi.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS Ayarlari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Statik Dosyalar ve Web Dashboard
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_dashboard():
    """Ana sayfada Web Dashboard arayuzunu sunar."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Skyblock Buffet API calisiyor!", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
