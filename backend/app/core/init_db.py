import asyncio
from app.core.database import engine, Base
import app.models # Modelleri kaydeder


async def init_db():
    """Tum SQLAlchemy modellerini PostgreSQL'de olusturur."""
    print("PostgreSQL tablolari olusturuluyor...")
    async with engine.begin() as conn:
        # Tablolari olustur (varsa dokunmaz)
        await conn.run_sync(Base.metadata.create_all)
    print("Tum tablolar basariyla hazirlandi!")


if __name__ == "__main__":
    asyncio.run(init_db())
