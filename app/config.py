from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    finnhub_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    app_env: str = "local"
    portfolio_json_path: str = "data/portfolio.json"
    tax_profile_json_path: str = "data/tax_profile.json"


def get_settings() -> Settings:
    return Settings()
