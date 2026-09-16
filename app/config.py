from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LINE_CHANNEL_SECRET: str = "placeholder_secret"
    LINE_CHANNEL_ACCESS_TOKEN: str = "placeholder_token"
    DEFAULT_SEARCH_RADIUS_KM: float = 5.0
    PORT: int = 8000

    # Niantic Campfire Configuration
    CAMPFIRE_AUTH_TOKEN: Optional[str] = None
    CAMPFIRE_API_ENDPOINT: str = "https://campfire.nianticlabs.com/api/graphql"
    CAMPFIRE_TIMEOUT_SECONDS: float = 6.0
    CAMPFIRE_CACHE_TTL_SECONDS: int = 60
    CAMPFIRE_FALLBACK_TO_MOCK: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

