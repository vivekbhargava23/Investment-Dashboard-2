"""
app/config/settings.py

Application settings loaded from environment variables.
Pydantic BaseSettings validates all values at startup —
if a required variable is missing or the wrong type,
the app fails immediately with a clear error message.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration object for the Investment Panel Dashboard.

    All values are loaded from the .env file in the project root.
    Types are validated by Pydantic at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development", description="Environment name")
    app_title: str = Field(
        default="Investment Panel Dashboard",
        description="Application display title",
    )

    # -------------------------------------------------------------------------
    # Finnhub API
    # -------------------------------------------------------------------------
    finnhub_api_key: str = Field(
        ...,  # ... means required — app will not start without this
        description="Finnhub API key for US equity price data",
    )

    # -------------------------------------------------------------------------
    # Price refresh
    # -------------------------------------------------------------------------
    price_refresh_interval_seconds: int = Field(
        default=60,
        ge=10,  # minimum 10 seconds — don't hammer the API
        description="How often to refresh live prices in seconds",
    )

    # -------------------------------------------------------------------------
    # German tax constants
    # -------------------------------------------------------------------------
    sparerpauschbetrag: float = Field(
        default=1000.00,
        description="Annual tax-free allowance in EUR (Sparerpauschbetrag)",
    )
    abgeltungsteuer_rate: float = Field(
        default=0.26375,
        description="German capital gains tax rate including solidarity surcharge",
    )

    # -------------------------------------------------------------------------
    # Convenience properties
    # -------------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        """True if running in development mode."""
        return self.app_env.lower() == "development"

    @property
    def sparerpauschbetrag_remaining(self) -> float:
        """
        Remaining allowance after known used amount.
        Updated manually — this is a static default.
        Actual tracking lives in the portfolio data store.
        """
        return self.sparerpauschbetrag


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Uses lru_cache so Settings is only instantiated once
    per application lifecycle — not on every import.

    Usage anywhere in the app:
        from app.config.settings import get_settings
        settings = get_settings()
        print(settings.finnhub_api_key)
    """
    return Settings()