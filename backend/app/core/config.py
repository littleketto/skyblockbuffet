from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    PROJECT_NAME: str = "Skyblock Buffet Economy Analyzer"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "skyblock_secret_key_super_secure_random_hash_987654321"
    DEBUG: bool = True

    # PostgreSQL Ayarları
    POSTGRES_USER: str = "skyblock"
    POSTGRES_PASSWORD: str = "change_me_in_production"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "skyblock_analyzer"

    # Hypixel API
    HYPIXEL_API_KEY: str = ""
    HYPIXEL_API_BASE: str = "https://api.hypixel.net/v2"

    # Skyblock Ekonomi Parametreleri
    # Standart Bazaar vergisi %1.125 (0.01125)
    BAZAAR_TAX_RATE: float = 0.01125

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Asenkron PostgreSQL baglanti URLi (asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
