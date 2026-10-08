"""Global configuration: read from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.2

    wos_api_key: str = ""
    wos_base_url: str = "https://api.clarivate.com/apis/wos-starter/v1"
    wos_max_requests: int = 60
    wos_min_interval: float = 1.1

    openalex_email: str = ""
    openalex_api_key: str = ""

    scib_cache_dir: Path = Path("artifacts/cache")
    scib_corpora_dir: Path = Path("artifacts/runs")
    scib_keep_history: bool = False
    scib_keep_cache: bool = False
    # Existing Obsidian vault to write runs into (as <vault>/SCIBooster/<run>/); empty = <run>/obsidian/ as its own vault
    scib_obsidian_vault: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
