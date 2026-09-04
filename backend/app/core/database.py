from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 1. Asenkron Veritabani Baglanti Motoru (Connection Engine)
# pool_pre_ping: Baglantinin kopup kopmadigini otomatik kontrol eder.
# pool_size: Havuzda hazir bekletilecek maksimum baglanti sayisi.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# 2. Oturum Ureticisi (Session Maker)
# Veritabaniyla yapacagimiz her islem (select, insert, update) bir oturum (session) uzerinden gecer.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 3. Tum Modellerin Miras Alacagi Temel Sinif (Base)
class Base(DeclarativeBase):
    pass


# 4. FastAPI Dependency (Bagimlilik Enjeksiyonu)
# Herhangi bir API endpointinde veritabanina erismek istedigimizde bu fonksiyon calisir,
# oturumu acar ve islem bittiginde guvenle kapatir.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
