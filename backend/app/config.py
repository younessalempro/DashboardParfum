"""
app/config.py
=============
Application settings loaded from environment variables / .env file.

Usage
-----
    from app.config import settings

    db_url = settings.database_url
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://parfums:parfums@localhost:5432/parfums"

    # API security
    admin_token: str = "change-me"

    # Scraper
    scraper_user_agent: str = "Mozilla/5.0 (compatible; PerfumeWatch/0.1)"
    scraper_request_delay_ms: int = 750
    playwright_headless: bool = True

    # CORS — comma-separated list of allowed origins
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
