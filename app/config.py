from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    finnhub_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    app_env: str = "local"
    portfolio_json_path: str = "data/portfolio.json"
    tax_profile_json_path: str = "data/tax_profile.json"
    ticker_cache_json_path: Path = Path("data/ticker_cache.json")
    nav_snapshots_json_path: Path = Path("data/nav_snapshots.json")
    isin_map_json_path: Path = Path("data/isin_map.json")


def get_settings() -> Settings:
    return Settings()
